// MatchController: playback clock, viewer profile and what's on screen, for demo and live modes.

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import 'data.dart';
import 'models.dart';

enum PlaybackMode { demo, live }

class MatchController extends ChangeNotifier {
  MatchController.demo({required this.matchId, required this.repo}) : mode = PlaybackMode.demo, liveBaseUrl = null;

  MatchController.live({required this.matchId, required this.repo, required String baseUrl})
    : mode = PlaybackMode.live,
      liveBaseUrl = baseUrl;

  static const speeds = [10.0, 30.0, 60.0, 120.0];
  static const _tick = Duration(milliseconds: 100);

  final String matchId;
  final DemoRepository repo;
  final PlaybackMode mode;
  final String? liveBaseUrl;

  // ---- data
  MatchMeta? meta;
  final List<MatchEvent> events = [];
  final List<OverlayCard> cards = [];
  final List<Handoff> handoffs = [];
  final List<StatsPoint> timeline = [];
  Recap? recap;
  Map<String, int> counters = {};
  List<String> llmChain = [];
  List<AskAnswer> qa = []; // demo: pre-asked; live: asked in this session
  bool asking = false;
  String? askError;
  String? error;
  bool loading = true;

  // ---- playback
  double clockMs = 0;
  bool playing = false;
  bool finished = false;
  double speed = 30;
  bool outage = false;
  int _revealed = 0; // events[0.._revealed) have happened
  Timer? _timer;

  // ---- viewer profile
  Audience audience = Audience.fan;
  Lang language = Lang.en;
  String? favouriteClubId;
  String? favouritePlayerId;

  // ---- on screen: card groups shown, with the real time they appeared
  final Map<String, Map<String, OverlayCard>> _byGroup = {}; // group -> "lang/audience" -> card
  final List<String> _dueGroups = []; // groups whose display time has passed, in order
  final Map<String, DateTime> _shownAt = {};
  int _nextCard = 0; // demo: cards sorted by display time; next one not yet due

  // live
  LiveClient? _live;
  StreamSubscription<Map<String, dynamic>>? _sub;

  bool get isLive => mode == PlaybackMode.live;

  // Deep-link actions the page performs once loaded (?drawer=1, ?recap=1).
  bool openDrawerOnLoad = false;
  bool openRecapOnLoad = false;
  bool openAskOnLoad = false;

  // ------------------------------------------------------------------ load

  Future<void> load() async {
    try {
      if (isLive) {
        await _startLive();
      } else {
        final m = await repo.match(matchId);
        final b = await repo.bundle(matchId);
        meta = m.meta;
        events.addAll(m.events);
        timeline.addAll(b.timeline);
        handoffs.addAll(b.handoffs);
        recap = b.recap;
        counters = b.counters;
        llmChain = b.llmChain;
        qa = b.qa;
        _addCards(b.cards);
        cards.sort((a, b) => a.displayAtMs.compareTo(b.displayAtMs));
      }
    } catch (e) {
      error = '$e';
    }
    loading = false;
    _timer = Timer.periodic(_tick, (_) => _onTick());
    notifyListeners();
  }

  void _addCards(Iterable<OverlayCard> incoming) {
    for (final c in incoming) {
      cards.add(c);
      (_byGroup[c.groupId] ??= {})['${c.language}/${c.audience}'] = c;
    }
  }

  // ------------------------------------------------------------- playback

  void _onTick() {
    final now = DateTime.now();
    var changed = false;
    if (!isLive && playing && !finished) {
      clockMs = math.min(clockMs + _tick.inMilliseconds * speed, events.last.ts.toDouble());
      if (clockMs >= events.last.ts) {
        finished = true;
        playing = false;
      }
      changed = true;
    }
    while (_revealed < events.length && events[_revealed].ts <= clockMs) {
      _revealed++;
    }
    if (!isLive) {
      while (_nextCard < cards.length && cards[_nextCard].displayAtMs <= clockMs) {
        _markDue(cards[_nextCard].groupId, now);
        _nextCard++;
        changed = true;
      }
    }
    // expire cards after their real-time reading window
    final before = _shownAt.length;
    _shownAt.removeWhere((group, at) => now.difference(at) > _readingTime(group));
    if (_shownAt.length != before) changed = true;
    if (changed) notifyListeners();
  }

  void _markDue(String group, DateTime now) {
    if (_dueGroups.contains(group)) return;
    _dueGroups.add(group);
    if (cardFor(group) != null) _shownAt[group] = now;
  }

  Duration _readingTime(String group) {
    final any = _byGroup[group]?.values.first;
    final secs = 6 + 6 * (any?.importance ?? 0).clamp(0, 1);
    return Duration(milliseconds: (secs * 1000).round());
  }

  void togglePlay() => playing ? pause() : play();

  void play() {
    if (finished && !isLive) restart();
    playing = true;
    if (isLive) _live?.send({'action': 'resume'});
    notifyListeners();
  }

  void pause() {
    playing = false;
    if (isLive) _live?.send({'action': 'pause'});
    notifyListeners();
  }

  void setSpeed(double value) {
    speed = value;
    if (isLive) _live?.send({'action': 'speed', 'value': value});
    notifyListeners();
  }

  void restart() {
    clockMs = 0;
    finished = false;
    _revealed = 0;
    _nextCard = 0;
    _dueGroups.clear();
    _shownAt.clear();
    notifyListeners();
  }

  /// Demo only: jump to a moment (e.g. straight to full time for the recap).
  /// With [showRecent], cards published in the last minute stay on screen.
  void seekTo(double ms, {bool showRecent = false}) {
    if (isLive) return;
    restart();
    clockMs = ms.clamp(0, events.last.ts.toDouble()).toDouble();
    _onTick();
    if (showRecent) {
      final now = DateTime.now();
      _shownAt.removeWhere((group, _) {
        final c = _byGroup[group]?.values.first;
        return c == null || c.displayAtMs < clockMs - 60000;
      });
      for (final g in _shownAt.keys.toList()) {
        _shownAt[g] = now;
      }
    } else {
      _shownAt.clear();
    }
    if (clockMs >= events.last.ts) finished = true;
    notifyListeners();
  }

  void setOutage(bool on) {
    outage = on;
    _live?.send({'action': 'outage', 'value': on});
    notifyListeners();
  }

  // ------------------------------------------------------------------ ask

  /// Live mode: ask the GitHub Copilot agent a question at the current match time.
  Future<void> ask(String question) async {
    if (!isLive || question.trim().length < 3 || asking) return;
    asking = true;
    askError = null;
    notifyListeners();
    try {
      final a = await askBackend(
        baseUrl: liveBaseUrl!,
        matchId: matchId,
        question: question.trim(),
        untilMs: clockMs.round(),
        language: language.wire,
      );
      qa = [a, ...qa];
    } catch (e) {
      askError = '$e';
    }
    asking = false;
    notifyListeners();
  }

  /// Demo mode: whether a pre-asked question is "unlocked" yet (no spoilers).
  bool qaUnlocked(AskAnswer a) => isLive || finished || a.untilMs <= clockMs;

  // -------------------------------------------------------------- profile

  void setAudience(Audience a) {
    audience = a;
    _profileChanged();
  }

  void setLanguage(Lang l) {
    language = l;
    _profileChanged();
  }

  void setFavouriteClub(String? clubId) {
    favouriteClubId = clubId;
    final club = clubId == null ? null : [meta!.home, meta!.away].firstWhere((c) => c.id == clubId);
    if (club == null || !club.players.any((p) => p.id == favouritePlayerId)) favouritePlayerId = null;
    _profileChanged();
  }

  void setFavouritePlayer(String? playerId) {
    favouritePlayerId = playerId;
    _profileChanged();
  }

  void _profileChanged() {
    // Demo: cards already exist for every profile, so the same moments re-render instantly.
    // Live: the server personalizes per session, so restart the session with the new profile.
    if (isLive && meta != null) {
      unawaited(_restartLive());
    }
    notifyListeners();
  }

  // ------------------------------------------------------------ derived

  Club? get favouriteClub =>
      favouriteClubId == null ? null : [meta!.home, meta!.away].firstWhere((c) => c.id == favouriteClubId);

  Player? get favouritePlayer => meta?.player(favouritePlayerId);

  StatsPoint? get point {
    if (timeline.isEmpty) return null;
    if (isLive) return timeline.last;
    final idx = (clockMs ~/ 60000).clamp(0, timeline.length - 1);
    return timeline[idx];
  }

  String get minuteLabel {
    if (finished) return 'FT';
    final p = point;
    if (p == null) return "0'";
    return clockMs <= 0 ? "0'" : p.minute;
  }

  int get scoreHome => _score(true);
  int get scoreAway => _score(false);

  int _score(bool home) {
    var n = 0;
    for (var i = 0; i < _revealed; i++) {
      final e = events[i];
      if (e.type == 'goal' && (e.team == Side.home) == home) n++;
    }
    return n;
  }

  List<StatsPoint> get momentumSoFar {
    if (isLive) return timeline;
    final t = clockMs ~/ 60000;
    return [
      for (final p in timeline)
        if (p.tMin <= t) p,
    ];
  }

  List<MatchEvent> get recentEvents {
    final out = <MatchEvent>[];
    for (var i = _revealed - 1; i >= 0 && out.length < 14; i--) {
      final e = events[i];
      if (e.x != null && e.team != null) out.add(e);
    }
    return out.reversed.toList();
  }

  List<MatchEvent> get revealedEvents => events.sublist(0, _revealed);

  /// The card variant for this group that fits the current viewer profile.
  OverlayCard? cardFor(String group) {
    final variants = _byGroup[group];
    if (variants == null) return null;
    final any = variants.values.first;
    if (any.type == 'commentary') {
      return variants['${language.wire}/fan'];
    }
    if (audience == Audience.playerFocus) {
      final focus = favouritePlayerId;
      final relevant = any.importance >= 0.85 || (focus != null && any.playerId == focus);
      if (!relevant) return null;
      return variants['${language.wire}/player_focus'] ?? variants['${language.wire}/fan'];
    }
    return variants['${language.wire}/${audience.wire}'];
  }

  /// Cards on screen now (most important first, at most 3).
  List<OverlayCard> get activeCards {
    final out = <OverlayCard>[];
    for (final g in _shownAt.keys) {
      final c = cardFor(g);
      if (c != null) out.add(c);
    }
    out.sort((a, b) => b.importance.compareTo(a.importance));
    return out.take(3).toList();
  }

  /// Everything published so far for this viewer, newest first.
  List<OverlayCard> get feed {
    final out = <OverlayCard>[];
    for (final g in _dueGroups.reversed) {
      final c = cardFor(g);
      if (c != null) out.add(c);
    }
    return out;
  }

  List<Handoff> get handoffsSoFar {
    if (isLive) return handoffs.reversed.take(300).toList();
    final shown = [
      for (final h in handoffs)
        if (h.matchMs <= clockMs) h,
    ];
    return shown.reversed.take(300).toList();
  }

  /// The recap card for this viewer (falls back to the English recap text).
  OverlayCard? get recapCard {
    for (final g in _dueGroups.reversed) {
      final c = _byGroup[g]?.values.first;
      if (c != null && c.type == 'recap') {
        return _byGroup[g]!['${language.wire}/${audience == Audience.analyst ? 'analyst' : 'fan'}'];
      }
    }
    return null;
  }

  bool isFavourite(Side? side) => side != null && favouriteClubId == meta?.club(side).id;

  // ----------------------------------------------------------------- live

  Map<String, String> _liveQuery() => {
    'speed': speed.toStringAsFixed(0),
    'audience': audience.wire,
    'language': language.wire,
    if (favouriteClub != null) 'club': favouriteClub!.name,
    if (favouritePlayer != null) 'player': favouritePlayer!.name,
    if (outage) 'outage': '1',
  };

  Future<void> _startLive() async {
    _live = LiveClient(baseUrl: liveBaseUrl!, matchId: matchId, query: _liveQuery());
    playing = true;
    _sub = _live!.connect().listen(
      _onLiveMessage,
      onError: (Object e) {
        error =
            'Live agents need the MatchMind backend, and none is answering at $liveBaseUrl.\n\n'
            'Open the repo in GitHub Codespaces, or run it locally with: '
            'uv run uvicorn matchmind.api.app:app';
        notifyListeners();
      },
    );
  }

  Future<void> _restartLive() async {
    await _sub?.cancel();
    await _live?.close();
    events.clear();
    cards.clear();
    handoffs.clear();
    timeline.clear();
    _byGroup.clear();
    recap = null;
    restart();
    await _startLive();
  }

  void _onLiveMessage(Map<String, dynamic> msg) {
    final now = DateTime.now();
    switch (msg['type']) {
      case 'hello':
        meta ??= MatchMeta.fromJson(msg['match'] as Map<String, dynamic>);
        final cfg = msg['config'] as Map<String, dynamic>;
        llmChain = [if (cfg['llm_enabled'] == true) 'live agents via ${cfg['stats_source']} stats'];
      case 'events':
        for (final e in msg['events'] as List) {
          events.add(MatchEvent.fromJson(e as Map<String, dynamic>));
        }
        clockMs = events.last.ts.toDouble();
      case 'stats':
        timeline.add(StatsPoint.fromJson(msg['point'] as Map<String, dynamic>));
      case 'cards':
        final incoming = [for (final c in msg['cards'] as List) OverlayCard.fromJson(c as Map<String, dynamic>)];
        _addCards(incoming);
        for (final c in incoming) {
          _markDue(c.groupId, now);
        }
      case 'handoffs':
        for (final h in msg['handoffs'] as List) {
          handoffs.add(Handoff.fromJson(h as Map<String, dynamic>));
        }
      case 'status':
        playing = !(msg['paused'] as bool);
        speed = (msg['speed'] as num).toDouble();
        outage = msg['outage'] as bool;
      case 'done':
        finished = true;
        playing = false;
        if (msg['recap'] != null) recap = Recap.fromJson(msg['recap'] as Map<String, dynamic>);
        counters = (msg['counters'] as Map<String, dynamic>).map((k, v) => MapEntry(k, (v as num).toInt()));
      case 'error':
        error = msg['message'] as String;
    }
    _onTick();
    notifyListeners();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _sub?.cancel();
    _live?.close();
    super.dispose();
  }
}

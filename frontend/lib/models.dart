// Data models mirroring the backend JSON (backend/src/matchmind/models.py, cards.py, state.py).

import 'dart:ui' show Color;

enum Side { home, away }

Side? sideFrom(Object? s) => switch (s) {
  'home' => Side.home,
  'away' => Side.away,
  _ => null,
};

Color parseHex(String hex) {
  final h = hex.replaceFirst('#', '');
  return Color(int.parse('FF$h', radix: 16));
}

double _d(Object? v) => (v as num?)?.toDouble() ?? 0.0;
int _i(Object? v) => (v as num?)?.toInt() ?? 0;

class Player {
  Player({required this.id, required this.name, required this.shirt, required this.position});

  factory Player.fromJson(Map<String, dynamic> j) => Player(
    id: j['id'] as String,
    name: j['name'] as String,
    shirt: _i(j['shirt']),
    position: j['position'] as String,
  );

  final String id;
  final String name;
  final int shirt;
  final String position;
}

class Club {
  Club({
    required this.id,
    required this.name,
    required this.shortName,
    required this.venue,
    required this.primary,
    required this.secondary,
    required this.players,
  });

  factory Club.fromJson(Map<String, dynamic> j) => Club(
    id: j['id'] as String,
    name: j['name'] as String,
    shortName: j['short_name'] as String,
    venue: j['venue'] as String,
    primary: parseHex(j['primary_color'] as String),
    secondary: parseHex(j['secondary_color'] as String),
    players: [for (final p in j['players'] as List) Player.fromJson(p as Map<String, dynamic>)],
  );

  final String id;
  final String name;
  final String shortName;
  final String venue;
  final Color primary;
  final Color secondary;
  final List<Player> players;
}

class MatchMeta {
  MatchMeta({
    required this.matchId,
    required this.story,
    required this.venue,
    required this.competition,
    required this.home,
    required this.away,
  });

  factory MatchMeta.fromJson(Map<String, dynamic> j) => MatchMeta(
    matchId: j['match_id'] as String,
    story: j['story'] as String,
    venue: j['venue'] as String,
    competition: j['competition'] as String,
    home: Club.fromJson(j['home'] as Map<String, dynamic>),
    away: Club.fromJson(j['away'] as Map<String, dynamic>),
  );

  final String matchId;
  final String story;
  final String venue;
  final String competition;
  final Club home;
  final Club away;

  Club club(Side side) => side == Side.home ? home : away;

  Player? player(String? id) {
    if (id == null) return null;
    for (final p in [...home.players, ...away.players]) {
      if (p.id == id) return p;
    }
    return null;
  }
}

class MatchEvent {
  MatchEvent({
    required this.id,
    required this.period,
    required this.minute,
    required this.ts,
    required this.type,
    this.team,
    this.playerId,
    this.relatedId,
    this.x,
    this.y,
    this.endX,
    this.endY,
    this.outcome,
  });

  factory MatchEvent.fromJson(Map<String, dynamic> j) => MatchEvent(
    id: j['event_id'] as String,
    period: _i(j['period']),
    minute: _i(j['minute']),
    ts: _i(j['timestamp_ms']),
    type: j['type'] as String,
    team: sideFrom(j['team']),
    playerId: j['player_id'] as String?,
    relatedId: j['related_player_id'] as String?,
    x: (j['x'] as num?)?.toDouble(),
    y: (j['y'] as num?)?.toDouble(),
    endX: (j['end_x'] as num?)?.toDouble(),
    endY: (j['end_y'] as num?)?.toDouble(),
    outcome: j['outcome'] as String?,
  );

  final String id;
  final int period;
  final int minute;
  final int ts;
  final String type;
  final Side? team;
  final String? playerId;
  final String? relatedId;
  final double? x;
  final double? y;
  final double? endX;
  final double? endY;
  final String? outcome;

  bool get onBall => type == 'pass' || type == 'carry' || type == 'shot';
}

class OverlayCard {
  OverlayCard({
    required this.id,
    required this.groupId,
    required this.momentId,
    required this.matchMinute,
    required this.period,
    required this.displayAtMs,
    required this.durationMs,
    required this.type,
    required this.audience,
    required this.language,
    required this.title,
    required this.body,
    this.why,
    this.team,
    this.playerId,
    required this.importance,
    required this.sourceAgent,
    this.provider,
    required this.fallbackUsed,
    required this.data,
  });

  factory OverlayCard.fromJson(Map<String, dynamic> j) => OverlayCard(
    id: j['id'] as String,
    groupId: j['group_id'] as String,
    momentId: (j['moment_id'] as String?) ?? '',
    matchMinute: _i(j['match_minute']),
    period: _i(j['period']),
    displayAtMs: _i(j['display_at_ms']),
    durationMs: _i(j['duration_ms']),
    type: j['type'] as String,
    audience: j['audience'] as String,
    language: j['language'] as String,
    title: j['title'] as String,
    body: j['body'] as String,
    why: j['why_it_matters'] as String?,
    team: sideFrom(j['team']),
    playerId: j['player_id'] as String?,
    importance: _d(j['importance']),
    sourceAgent: j['source_agent'] as String,
    provider: j['provider'] as String?,
    fallbackUsed: (j['fallback_used'] as bool?) ?? false,
    data: (j['data'] as Map<String, dynamic>?) ?? const {},
  );

  final String id;
  final String groupId;
  final String momentId;
  final int matchMinute;
  final int period;
  final int displayAtMs;
  final int durationMs;
  final String type;
  final String audience;
  final String language;
  final String title;
  final String body;
  final String? why;
  final Side? team;
  final String? playerId;
  final double importance;
  final String sourceAgent;
  final String? provider;
  final bool fallbackUsed;
  final Map<String, dynamic> data;

  String get kind => momentId.split(':').first;
}

class StatsPoint {
  StatsPoint({
    required this.tMin,
    required this.minute,
    required this.period,
    required this.scoreHome,
    required this.scoreAway,
    required this.momentum,
    required this.possessionHome,
    required this.pressureHome,
    required this.pressureAway,
    required this.chaosIndex,
    required this.chaosLabel,
  });

  factory StatsPoint.fromJson(Map<String, dynamic> j) => StatsPoint(
    tMin: _i(j['t_min']),
    minute: j['minute'] as String,
    period: _i(j['period']),
    scoreHome: _i(j['score_home']),
    scoreAway: _i(j['score_away']),
    momentum: _d(j['momentum']),
    possessionHome: _d(j['possession_home']),
    pressureHome: _d(j['pressure_home']),
    pressureAway: _d(j['pressure_away']),
    chaosIndex: _d(j['chaos_index']),
    chaosLabel: j['chaos_label'] as String,
  );

  final int tMin;
  final String minute;
  final int period;
  final int scoreHome;
  final int scoreAway;
  final double momentum;
  final double possessionHome;
  final double pressureHome;
  final double pressureAway;
  final double chaosIndex;
  final String chaosLabel;
}

class Handoff {
  Handoff({
    required this.seq,
    required this.matchMs,
    required this.source,
    required this.target,
    required this.status,
    required this.detail,
    this.momentId,
    this.provider,
    this.latencyMs,
  });

  factory Handoff.fromJson(Map<String, dynamic> j) => Handoff(
    seq: _i(j['seq']),
    matchMs: _i(j['match_ms']),
    source: j['source'] as String,
    target: j['target'] as String,
    status: j['status'] as String,
    detail: (j['detail'] as String?) ?? '',
    momentId: j['moment_id'] as String?,
    provider: j['provider'] as String?,
    latencyMs: (j['latency_ms'] as num?)?.toInt(),
  );

  final int seq;
  final int matchMs;
  final String source;
  final String target;
  final String status;
  final String detail;
  final String? momentId;
  final String? provider;
  final int? latencyMs;
}

class Recap {
  Recap({required this.headline, required this.summary, required this.turningPoints});

  factory Recap.fromJson(Map<String, dynamic> j) => Recap(
    headline: j['headline'] as String,
    summary: j['summary'] as String,
    turningPoints: [for (final t in j['turning_points'] as List) t as String],
  );

  final String headline;
  final String summary;
  final List<String> turningPoints;
}

class MatchSummary {
  MatchSummary({
    required this.matchId,
    required this.title,
    required this.story,
    required this.home,
    required this.away,
    required this.venue,
  });

  factory MatchSummary.fromJson(Map<String, dynamic> j) => MatchSummary(
    matchId: j['match_id'] as String,
    title: j['title'] as String,
    story: j['story'] as String,
    home: j['home'] as String,
    away: j['away'] as String,
    venue: j['venue'] as String,
  );

  final String matchId;
  final String title;
  final String story;
  final String home;
  final String away;
  final String venue;
}

enum Audience {
  fan('fan', 'Fan'),
  analyst('analyst', 'Analyst'),
  playerFocus('player_focus', 'Player focus');

  const Audience(this.wire, this.label);
  final String wire;
  final String label;
}

enum Lang {
  en('en', 'English', false),
  ur('ur', 'اردو', true),
  ar('ar', 'العربية', true);

  const Lang(this.wire, this.label, this.rtl);
  final String wire;
  final String label;
  final bool rtl;
}

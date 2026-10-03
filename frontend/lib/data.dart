// Data sources: bundled demo assets (no backend) and the live WebSocket API.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

import 'models.dart';

class LoadedMatch {
  LoadedMatch(this.meta, this.events);
  final MatchMeta meta;
  final List<MatchEvent> events;
}

class DemoBundle {
  DemoBundle({
    required this.cards,
    required this.handoffs,
    required this.timeline,
    required this.recap,
    required this.counters,
    required this.llmChain,
    required this.qa,
  });

  factory DemoBundle.fromJson(Map<String, dynamic> j) => DemoBundle(
    cards: [for (final c in j['cards'] as List) OverlayCard.fromJson(c as Map<String, dynamic>)],
    handoffs: [for (final h in j['handoffs'] as List) Handoff.fromJson(h as Map<String, dynamic>)],
    timeline: [for (final p in j['timeline'] as List) StatsPoint.fromJson(p as Map<String, dynamic>)],
    recap: j['recap'] == null ? null : Recap.fromJson(j['recap'] as Map<String, dynamic>),
    counters: (j['counters'] as Map<String, dynamic>).map((k, v) => MapEntry(k, (v as num).toInt())),
    llmChain: [for (final s in (j['pipeline'] as Map<String, dynamic>)['llm_chain'] as List) s as String],
    qa: [for (final a in (j['qa'] as List? ?? const [])) AskAnswer.fromJson(a as Map<String, dynamic>)],
  );

  final List<OverlayCard> cards;
  final List<Handoff> handoffs;
  final List<StatsPoint> timeline;
  final Recap? recap;
  final Map<String, int> counters;
  final List<String> llmChain;
  final List<AskAnswer> qa;
}

/// POST /api/ask on the live backend.
Future<AskAnswer> askBackend({
  required String baseUrl,
  required String matchId,
  required String question,
  required int untilMs,
  required String language,
}) async {
  final res = await http.post(
    Uri.parse(baseUrl).replace(path: '/api/ask'),
    headers: {'content-type': 'application/json'},
    body: jsonEncode({'match_id': matchId, 'question': question, 'until_ms': untilMs, 'language': language}),
  );
  if (res.statusCode != 200) throw Exception('Ask failed (${res.statusCode}): ${res.body}');
  return AskAnswer.fromJson(jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>);
}

class DemoRepository {
  static Future<Map<String, dynamic>> _json(String path) async =>
      jsonDecode(await rootBundle.loadString(path)) as Map<String, dynamic>;

  Future<List<MatchSummary>> matches() async {
    final raw = jsonDecode(await rootBundle.loadString('assets/data/index.json')) as List;
    return [for (final m in raw) MatchSummary.fromJson(m as Map<String, dynamic>)];
  }

  Future<LoadedMatch> match(String id) async {
    final j = await _json('assets/data/matches/$id.json');
    return LoadedMatch(MatchMeta.fromJson(j['meta'] as Map<String, dynamic>), [
      for (final e in j['events'] as List) MatchEvent.fromJson(e as Map<String, dynamic>),
    ]);
  }

  Future<DemoBundle> bundle(String id) async => DemoBundle.fromJson(await _json('assets/data/demo/$id.json'));
}

/// One live session against the backend (`/ws/live/{id}`). Messages are documented in
/// backend/src/matchmind/api/live.py.
class LiveClient {
  LiveClient({required String baseUrl, required String matchId, required Map<String, String> query})
    : uri = Uri.parse(
        baseUrl.replaceFirst(RegExp('^http'), 'ws'),
      ).replace(path: '/ws/live/$matchId', queryParameters: query);

  final Uri uri;
  WebSocketChannel? _channel;

  Stream<Map<String, dynamic>> connect() {
    _channel = WebSocketChannel.connect(uri);
    return _channel!.stream.map((raw) => jsonDecode(raw as String) as Map<String, dynamic>);
  }

  void send(Map<String, Object?> action) => _channel?.sink.add(jsonEncode(action));

  Future<void> close() async => _channel?.sink.close();
}

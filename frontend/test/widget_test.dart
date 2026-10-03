import 'package:flutter_test/flutter_test.dart';
import 'package:matchmind_app/models.dart';

void main() {
  test('overlay card parses from backend JSON', () {
    final c = OverlayCard.fromJson({
      'id': 'goal:e00612:ur:fan',
      'group_id': 'goal:e00612',
      'moment_id': 'goal:e00612',
      'match_minute': 58,
      'period': 2,
      'display_at_ms': 3534000,
      'duration_ms': 12000,
      'type': 'insight',
      'audience': 'fan',
      'language': 'ur',
      'title': 'گول!',
      'body': 'body',
      'importance': 1.0,
      'source_agent': 'insight_agent+personalizer_agent',
      'team': 'home',
      'data': {'xg': 0.27},
    });
    expect(c.kind, 'goal');
    expect(c.team, Side.home);
    expect(c.fallbackUsed, false);
    expect(c.data['xg'], 0.27);
  });

  test('languages know their direction', () {
    expect(Lang.en.rtl, isFalse);
    expect(Lang.ur.rtl, isTrue);
    expect(Lang.ar.rtl, isTrue);
  });
}

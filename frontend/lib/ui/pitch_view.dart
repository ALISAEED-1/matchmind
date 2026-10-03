import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models.dart';
import '../theme.dart';

/// 2D pitch (105 x 68) with the most recent events. Home attacks left -> right.
class PitchView extends StatelessWidget {
  const PitchView({super.key, required this.events, required this.home, required this.away, this.focusPlayerId});

  final List<MatchEvent> events;
  final Color home;
  final Color away;
  final String? focusPlayerId;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 105 / 68,
      child: CustomPaint(painter: _PitchPainter(events, home, away, focusPlayerId)),
    );
  }
}

class _PitchPainter extends CustomPainter {
  _PitchPainter(this.events, this.home, this.away, this.focus);

  final List<MatchEvent> events;
  final Color home;
  final Color away;
  final String? focus;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    Offset p(double x, double y) => Offset(x / 100 * w, (1 - y / 100) * h);

    // grass with subtle stripes
    final rrect = RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(12));
    canvas.save();
    canvas.clipRRect(rrect);
    canvas.drawRect(Offset.zero & size, Paint()..color = MM.pitch);
    final stripe = Paint()..color = const Color(0x0DFFFFFF);
    for (var i = 0; i < 10; i += 2) {
      canvas.drawRect(Rect.fromLTWH(i * w / 10, 0, w / 10, h), stripe);
    }

    // markings
    final line = Paint()
      ..color = MM.pitchLine
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    canvas.drawRect(Rect.fromLTWH(4, 4, w - 8, h - 8), line);
    canvas.drawLine(Offset(w / 2, 4), Offset(w / 2, h - 4), line);
    canvas.drawCircle(Offset(w / 2, h / 2), h * 9.15 / 68, line);
    final boxW = w * 16.5 / 105, boxH = h * 40.3 / 68;
    final sixW = w * 5.5 / 105, sixH = h * 18.3 / 68;
    for (final left in [true, false]) {
      final x0 = left ? 4.0 : w - 4 - boxW;
      canvas.drawRect(Rect.fromLTWH(x0, (h - boxH) / 2, boxW, boxH), line);
      final s0 = left ? 4.0 : w - 4 - sixW;
      canvas.drawRect(Rect.fromLTWH(s0, (h - sixH) / 2, sixW, sixH), line);
    }

    // events: older ones fade
    for (var i = 0; i < events.length; i++) {
      final e = events[i];
      final age = (events.length - 1 - i) / math.max(1, events.length - 1);
      final focused = focus != null && (e.playerId == focus || e.relatedId == focus);
      final base = e.team == Side.home ? home : away;
      final alpha = focused ? 1.0 : (focus != null ? 0.25 : 0.25 + 0.75 * (1 - age));
      final color = base.withValues(alpha: alpha);
      final from = p(e.x!, e.y!);
      final to = e.endX != null ? p(e.endX!, e.endY!) : null;

      switch (e.type) {
        case 'pass':
          if (to == null) break;
          final failed = e.outcome != 'complete';
          _arrow(canvas, from, to, failed ? const Color(0xFFFF5252).withValues(alpha: alpha) : color, focused ? 3 : 2);
        case 'carry':
          if (to == null) break;
          _dashed(canvas, from, to, color);
        case 'shot':
          if (to == null) break;
          final goal = e.outcome == 'goal';
          _arrow(canvas, from, to, (goal ? MM.primary : MM.highlight).withValues(alpha: alpha), 3.5);
          canvas.drawCircle(from, 6, Paint()..color = MM.highlight.withValues(alpha: alpha));
        case 'tackle' || 'interception' || 'foul':
          final pen = Paint()
            ..color = color
            ..strokeWidth = 2.5;
          canvas.drawLine(from + const Offset(-5, -5), from + const Offset(5, 5), pen);
          canvas.drawLine(from + const Offset(-5, 5), from + const Offset(5, -5), pen);
        default:
          canvas.drawCircle(from, 3, Paint()..color = color);
      }
    }

    // ball at the latest action
    if (events.isNotEmpty) {
      final last = events.last;
      final ball = last.endX != null ? p(last.endX!, last.endY!) : p(last.x!, last.y!);
      canvas.drawCircle(ball, 7, Paint()..color = Colors.white);
      canvas.drawCircle(
        ball,
        7,
        Paint()
          ..color = Colors.black
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5,
      );
    }
    canvas.restore();
  }

  void _arrow(Canvas c, Offset a, Offset b, Color color, double width) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = width
      ..strokeCap = StrokeCap.round;
    c.drawLine(a, b, paint);
    final angle = math.atan2(b.dy - a.dy, b.dx - a.dx);
    const head = 9.0;
    final path = Path()
      ..moveTo(b.dx, b.dy)
      ..lineTo(b.dx - head * math.cos(angle - 0.45), b.dy - head * math.sin(angle - 0.45))
      ..lineTo(b.dx - head * math.cos(angle + 0.45), b.dy - head * math.sin(angle + 0.45))
      ..close();
    c.drawPath(path, Paint()..color = color);
  }

  void _dashed(Canvas c, Offset a, Offset b, Color color) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1.5;
    final total = (b - a).distance;
    if (total == 0) return;
    final dir = (b - a) / total;
    for (double d = 0; d < total; d += 8) {
      c.drawLine(a + dir * d, a + dir * math.min(d + 4, total), paint);
    }
  }

  @override
  bool shouldRepaint(_PitchPainter old) =>
      old.events.length != events.length ||
      (events.isNotEmpty && old.events.isNotEmpty && old.events.last.id != events.last.id) ||
      old.focus != focus;
}

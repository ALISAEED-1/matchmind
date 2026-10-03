import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../controller.dart';
import '../models.dart';
import '../theme.dart';

class Scoreboard extends StatelessWidget {
  const Scoreboard({super.key, required this.c});

  final MatchController c;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final m = c.meta!;
    Widget team(Club club, Side side) => Expanded(
      child: Row(
        mainAxisAlignment: side == Side.home ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (side == Side.away) _crest(club),
          if (side == Side.away) const SizedBox(width: 10),
          Flexible(
            child: Text(
              club.name,
              overflow: TextOverflow.ellipsis,
              textAlign: side == Side.home ? TextAlign.end : TextAlign.start,
              style: t.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
                color: c.isFavourite(side) ? MM.highlight : MM.text,
              ),
            ),
          ),
          if (side == Side.home) const SizedBox(width: 10),
          if (side == Side.home) _crest(club),
        ],
      ),
    );
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(color: MM.surface, borderRadius: BorderRadius.circular(12)),
      child: Row(
        children: [
          team(m.home, Side.home),
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 14),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
            decoration: BoxDecoration(color: MM.background, borderRadius: BorderRadius.circular(8)),
            child: Text(
              '${c.scoreHome} - ${c.scoreAway}',
              style: t.headlineSmall?.copyWith(fontWeight: FontWeight.w900, fontFeatures: const []),
            ),
          ),
          team(m.away, Side.away),
        ],
      ),
    );
  }

  Widget _crest(Club club) => Container(
    width: 26,
    height: 26,
    alignment: Alignment.center,
    decoration: BoxDecoration(
      color: club.primary,
      shape: BoxShape.circle,
      border: Border.all(color: club.secondary, width: 2),
    ),
    child: Text(
      club.id[0],
      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w900, color: Colors.white),
    ),
  );
}

class MomentumChart extends StatelessWidget {
  const MomentumChart({super.key, required this.c});

  final MatchController c;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final pts = c.momentumSoFar;
    final m = c.meta!;
    final spots = [for (final p in pts) FlSpot(p.tMin.toDouble(), p.momentum)];
    final maxX = c.isLive ? (spots.isEmpty ? 95.0 : spots.last.x.clamp(10, 100).toDouble()) : 97.0;
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 16, 6),
      decoration: BoxDecoration(color: MM.surface, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('MOMENTUM', style: t.labelSmall?.copyWith(color: MM.muted, letterSpacing: 1.2)),
              const Spacer(),
              _legend(m.home.shortName, m.home.primary),
              const SizedBox(width: 12),
              _legend(m.away.shortName, m.away.primary),
            ],
          ),
          const SizedBox(height: 6),
          SizedBox(
            height: 110,
            child: LineChart(
              duration: Duration.zero,
              LineChartData(
                minX: 0,
                maxX: maxX,
                minY: -1,
                maxY: 1,
                gridData: FlGridData(
                  drawVerticalLine: false,
                  horizontalInterval: 1,
                  getDrawingHorizontalLine: (v) =>
                      FlLine(color: v == 0 ? MM.muted : Colors.transparent, strokeWidth: 1, dashArray: [4, 4]),
                ),
                titlesData: FlTitlesData(
                  leftTitles: const AxisTitles(),
                  topTitles: const AxisTitles(),
                  rightTitles: const AxisTitles(),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      interval: 15,
                      reservedSize: 18,
                      getTitlesWidget: (v, _) =>
                          Text("${v.toInt()}'", style: const TextStyle(fontSize: 10, color: MM.muted)),
                    ),
                  ),
                ),
                borderData: FlBorderData(show: false),
                lineTouchData: const LineTouchData(enabled: false),
                lineBarsData: [
                  LineChartBarData(
                    spots: spots.isEmpty ? [const FlSpot(0, 0)] : spots,
                    isCurved: true,
                    curveSmoothness: 0.2,
                    barWidth: 2,
                    color: MM.text,
                    dotData: const FlDotData(show: false),
                    aboveBarData: BarAreaData(
                      show: true,
                      cutOffY: 0,
                      applyCutOffY: true,
                      color: m.away.primary.withValues(alpha: 0.35),
                    ),
                    belowBarData: BarAreaData(
                      show: true,
                      cutOffY: 0,
                      applyCutOffY: true,
                      color: m.home.primary.withValues(alpha: 0.35),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _legend(String name, Color color) => Row(
    children: [
      Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      ),
      const SizedBox(width: 4),
      Text(name, style: const TextStyle(fontSize: 11, color: MM.muted)),
    ],
  );
}

/// Live numbers for analyst mode: possession, pressing and the control-vs-chaos reading.
class StatsPanel extends StatelessWidget {
  const StatsPanel({super.key, required this.c});

  final MatchController c;

  @override
  Widget build(BuildContext context) {
    final p = c.point;
    final t = Theme.of(context).textTheme;
    final m = c.meta!;
    if (p == null || c.clockMs == 0) return const SizedBox.shrink();
    Widget bar(String label, double home, double away, String Function(double) fmt) {
      final total = (home + away) == 0 ? 1 : home + away;
      return Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(fmt(home), style: t.bodySmall?.copyWith(fontWeight: FontWeight.w700)),
                const Spacer(),
                Text(label, style: t.labelSmall?.copyWith(color: MM.muted)),
                const Spacer(),
                Text(fmt(away), style: t.bodySmall?.copyWith(fontWeight: FontWeight.w700)),
              ],
            ),
            const SizedBox(height: 4),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: Row(
                children: [
                  Expanded(
                    flex: (home / total * 1000).round().clamp(1, 1000),
                    child: Container(height: 6, color: m.home.primary),
                  ),
                  Expanded(
                    flex: (away / total * 1000).round().clamp(1, 1000),
                    child: Container(height: 6, color: m.away.primary),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
    }

    final chaosColor = switch (p.chaosLabel) {
      'chaotic' => const Color(0xFFFF5252),
      'controlled' => MM.primary,
      _ => MM.highlight,
    };
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: MM.surface, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('MATCH NUMBERS', style: t.labelSmall?.copyWith(color: MM.muted, letterSpacing: 1.2)),
          const SizedBox(height: 10),
          bar('Possession', p.possessionHome, 1 - p.possessionHome, (v) => '${(v * 100).round()}%'),
          bar('Pressure (10 min)', p.pressureHome, p.pressureAway, (v) => v.toStringAsFixed(2)),
          Row(
            children: [
              Text('Game state (10 min)', style: t.labelSmall?.copyWith(color: MM.muted)),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: chaosColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  '${p.chaosLabel} · ${p.chaosIndex.toStringAsFixed(2)}',
                  style: t.labelSmall?.copyWith(color: chaosColor, fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

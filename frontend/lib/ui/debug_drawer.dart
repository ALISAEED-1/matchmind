import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controller.dart';
import '../models.dart';
import '../theme.dart';

/// Judge-facing view of the multi-agent system: every hand-off, retry and fallback.
class DebugDrawer extends StatelessWidget {
  const DebugDrawer({super.key});

  @override
  Widget build(BuildContext context) {
    final c = context.watch<MatchController>();
    final t = Theme.of(context).textTheme;
    final handoffs = c.handoffsSoFar;
    final counts = <String, int>{};
    for (final h in c.isLive ? c.handoffs : c.handoffs.where((h) => h.matchMs <= c.clockMs)) {
      counts[h.status] = (counts[h.status] ?? 0) + 1;
    }

    return Drawer(
      width: 440,
      backgroundColor: MM.background,
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Agent handoffs', style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 4),
                  Text(
                    'stats_agent → producer → insight / narrator / personalizer → verifier → publisher. '
                    'Every LLM answer is checked by the verifier; failures retry, fall back to the next '
                    'model, then to a verified template.',
                    style: t.bodySmall?.copyWith(color: MM.muted),
                  ),
                  if (c.llmChain.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text('Models: ${c.llmChain.join(' → ')}', style: t.labelSmall?.copyWith(color: MM.muted)),
                  ],
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      for (final s in ['ok', 'cached', 'retry', 'provider_fallback', 'fallback', 'skipped'])
                        if ((counts[s] ?? 0) > 0) _statusChip('$s ${counts[s]}', s),
                    ],
                  ),
                  if (c.isLive) ...[
                    const SizedBox(height: 8),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      value: c.outage,
                      onChanged: c.setOutage,
                      activeColor: MM.statusColor('fallback'),
                      title: const Text('Simulate model outage'),
                      subtitle: const Text('Every model fails with a 503: watch the recovery path'),
                    ),
                  ],
                ],
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: handoffs.isEmpty
                  ? Center(
                      child: Text('Press play to start the match', style: t.bodyMedium?.copyWith(color: MM.muted)),
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      itemCount: handoffs.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 2),
                      itemBuilder: (_, i) => _HandoffRow(h: handoffs[i]),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

Widget _statusChip(String text, String status) {
  final color = MM.statusColor(status);
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.12),
      borderRadius: BorderRadius.circular(6),
      border: Border.all(color: color.withValues(alpha: 0.5)),
    ),
    child: Text(
      text,
      style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600),
    ),
  );
}

class _HandoffRow extends StatelessWidget {
  const _HandoffRow({required this.h});

  final Handoff h;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final minute = '${h.matchMs ~/ 60000 + 1}\'';
    final color = MM.statusColor(h.status);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 34,
            child: Text(minute, style: t.labelSmall?.copyWith(color: MM.muted)),
          ),
          Container(width: 3, height: 34, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        '${h.source} → ${h.target}',
                        overflow: TextOverflow.ellipsis,
                        style: t.bodySmall?.copyWith(fontWeight: FontWeight.w700),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(h.status, style: TextStyle(fontSize: 10, color: color)),
                    if (h.latencyMs != null) ...[
                      const SizedBox(width: 6),
                      Text(
                        '${(h.latencyMs! / 1000).toStringAsFixed(1)}s',
                        style: t.labelSmall?.copyWith(color: MM.muted),
                      ),
                    ],
                  ],
                ),
                if (h.detail.isNotEmpty)
                  Text(
                    h.detail,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: t.labelSmall?.copyWith(color: MM.muted),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

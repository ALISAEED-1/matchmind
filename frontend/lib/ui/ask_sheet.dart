import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controller.dart';
import '../models.dart';
import '../theme.dart';

void showAsk(BuildContext context) {
  final c = context.read<MatchController>();
  showModalBottomSheet<void>(
    context: context,
    backgroundColor: MM.surface,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (_) => ChangeNotifierProvider.value(value: c, child: const _AskSheet()),
  );
}

class _AskSheet extends StatefulWidget {
  const _AskSheet();

  @override
  State<_AskSheet> createState() => _AskSheetState();
}

class _AskSheetState extends State<_AskSheet> {
  final _q = TextEditingController();
  AskAnswer? _open;

  @override
  Widget build(BuildContext context) {
    final c = context.watch<MatchController>();
    final t = Theme.of(context).textTheme;
    final height = MediaQuery.sizeOf(context).height * 0.8;

    return SafeArea(
      child: SizedBox(
        height: height,
        child: Padding(
          padding: EdgeInsets.fromLTRB(20, 0, 20, 16 + MediaQuery.viewInsetsOf(context).bottom),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.forum_outlined, color: MM.primary),
                  const SizedBox(width: 8),
                  Text('Ask MatchMind', style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                'Answered by a GitHub Copilot agent (Microsoft Agent Framework) that looks the facts up '
                'with the matchmind-stats MCP tools, only up to the current minute.',
                style: t.bodySmall?.copyWith(color: MM.muted),
              ),
              const SizedBox(height: 14),
              if (c.isLive) ...[
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _q,
                        enabled: !c.asking,
                        decoration: const InputDecoration(
                          hintText: 'e.g. Why are they on top? Who is the best player so far?',
                          border: OutlineInputBorder(),
                          isDense: true,
                        ),
                        onSubmitted: (v) => _send(c),
                      ),
                    ),
                    const SizedBox(width: 8),
                    FilledButton(
                      onPressed: c.asking ? null : () => _send(c),
                      child: c.asking
                          ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                          : const Text('Ask'),
                    ),
                  ],
                ),
                if (c.askError != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(c.askError!, style: const TextStyle(color: Color(0xFFFF5252))),
                  ),
                const SizedBox(height: 12),
              ] else
                Text(
                  'Suggested questions (unlock as the match reaches them):',
                  style: t.labelMedium?.copyWith(color: MM.muted),
                ),
              const SizedBox(height: 8),
              Expanded(
                child: c.qa.isEmpty
                    ? Center(
                        child: Text(
                          c.isLive ? 'Ask anything about the match so far.' : 'No questions for this match.',
                          style: t.bodyMedium?.copyWith(color: MM.muted),
                        ),
                      )
                    : ListView.separated(
                        itemCount: c.qa.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 10),
                        itemBuilder: (_, i) => _QaTile(
                          a: c.qa[i],
                          unlocked: c.qaUnlocked(c.qa[i]),
                          expanded: c.isLive || identical(_open, c.qa[i]),
                          onTap: () => setState(() => _open = identical(_open, c.qa[i]) ? null : c.qa[i]),
                        ),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _send(MatchController c) {
    final q = _q.text;
    if (q.trim().length < 3) return;
    _q.clear();
    c.ask(q);
  }
}

class _QaTile extends StatelessWidget {
  const _QaTile({required this.a, required this.unlocked, required this.expanded, required this.onTap});

  final AskAnswer a;
  final bool unlocked;
  final bool expanded;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final lang = Lang.values.firstWhere((l) => l.wire == a.language, orElse: () => Lang.en);
    final copilot = a.provider == 'github-copilot';
    return Opacity(
      opacity: unlocked ? 1 : 0.45,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: unlocked ? onTap : null,
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: MM.surfaceHigh,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: MM.primary.withValues(alpha: expanded ? 0.6 : 0.15)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    a.minute,
                    style: t.labelSmall?.copyWith(color: MM.highlight, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Directionality(
                      textDirection: lang.rtl ? TextDirection.rtl : TextDirection.ltr,
                      child: Text(
                        a.question,
                        style: langStyle(lang, t.titleSmall!.copyWith(fontWeight: FontWeight.w700)),
                      ),
                    ),
                  ),
                  Icon(unlocked ? (expanded ? Icons.expand_less : Icons.expand_more) : Icons.lock_outline, size: 18),
                ],
              ),
              if (unlocked && expanded) ...[
                const SizedBox(height: 10),
                Directionality(
                  textDirection: lang.rtl ? TextDirection.rtl : TextDirection.ltr,
                  child: Text(a.answer, style: langStyle(lang, t.bodyMedium!)),
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    _chip(copilot ? 'GitHub Copilot' : a.provider, copilot ? MM.primary : MM.statusColor('fallback')),
                    for (final tool in a.toolsUsed) _chip('MCP · $tool', const Color(0xFF4FC3F7)),
                    _chip('${(a.latencyMs / 1000).toStringAsFixed(0)} s', MM.muted),
                  ],
                ),
              ],
              if (!unlocked)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text('Unlocks at ${a.minute}', style: t.labelSmall?.copyWith(color: MM.muted)),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _chip(String text, Color color) => Container(
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

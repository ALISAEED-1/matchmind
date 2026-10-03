import 'package:flutter/material.dart';

import '../models.dart';
import '../theme.dart';

const _typeLabel = {
  Lang.en: {'insight': 'INSIGHT', 'stat': 'STAT', 'commentary': 'LIVE', 'milestone': 'MILESTONE', 'recap': 'FULL TIME'},
  Lang.ur: {
    'insight': 'تجزیہ',
    'stat': 'اعداد و شمار',
    'commentary': 'براہ راست',
    'milestone': 'سنگ میل',
    'recap': 'میچ ختم',
  },
  Lang.ar: {
    'insight': 'تحليل',
    'stat': 'إحصائية',
    'commentary': 'مباشر',
    'milestone': 'إنجاز',
    'recap': 'نهاية المباراة',
  },
};

const _whyLabel = {Lang.en: 'Why it matters', Lang.ur: 'یہ کیوں اہم ہے', Lang.ar: 'لماذا يهم'};

/// One overlay card. `compact` is used in the side feed.
class CardTile extends StatelessWidget {
  const CardTile({
    super.key,
    required this.card,
    required this.lang,
    this.compact = false,
    this.favourite = false,
    this.showSource = false,
    this.minute,
  });

  final OverlayCard card;
  final Lang lang;
  final bool compact;
  final bool favourite;
  final bool showSource;
  final String? minute;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final color = MM.cardColor(card.type);
    final cardLang = Lang.values.firstWhere((l) => l.wire == card.language, orElse: () => Lang.en);
    final title = langStyle(cardLang, (compact ? t.titleSmall : t.titleMedium)!.copyWith(fontWeight: FontWeight.w800));
    final body = langStyle(cardLang, (compact ? t.bodySmall : t.bodyMedium)!.copyWith(color: MM.text));
    final why = langStyle(cardLang, t.bodySmall!.copyWith(color: MM.muted, fontStyle: FontStyle.italic));

    return Directionality(
      textDirection: cardLang.rtl ? TextDirection.rtl : TextDirection.ltr,
      child: Container(
        decoration: BoxDecoration(
          color: MM.surface.withValues(alpha: compact ? 1 : 0.94),
          borderRadius: BorderRadius.circular(12),
          border: BorderDirectional(start: BorderSide(color: color, width: 4)),
          boxShadow: compact ? null : const [BoxShadow(color: Colors.black54, blurRadius: 16)],
        ),
        padding: EdgeInsets.all(compact ? 10 : 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Text(
                  _typeLabel[cardLang]![card.type] ?? card.type.toUpperCase(),
                  style: langStyle(cardLang, t.labelSmall!.copyWith(color: color, letterSpacing: 1.1)),
                ),
                if (minute != null) ...[
                  const SizedBox(width: 8),
                  Text(minute!, style: t.labelSmall?.copyWith(color: MM.muted)),
                ],
                if (favourite) ...[const SizedBox(width: 8), const Icon(Icons.favorite, size: 14, color: MM.highlight)],
                const Spacer(),
                if (card.fallbackUsed)
                  Tooltip(
                    message: 'Every model failed for this card; a verified template was used.',
                    child: _chip('template fallback', MM.statusColor('fallback')),
                  ),
              ],
            ),
            const SizedBox(height: 6),
            Text(card.title, style: title),
            const SizedBox(height: 4),
            Text(card.body, style: body),
            if (card.why != null && card.why!.isNotEmpty && !compact) ...[
              const SizedBox(height: 8),
              Text('${_whyLabel[cardLang]}: ${card.why}', style: why),
            ],
            if (showSource) ...[
              const SizedBox(height: 8),
              Directionality(
                textDirection: TextDirection.ltr,
                child: Text(
                  '${card.sourceAgent}${card.provider != null ? ' · ${card.provider}' : ''}',
                  style: t.labelSmall?.copyWith(color: MM.muted),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _chip(String text, Color color) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.15),
      borderRadius: BorderRadius.circular(6),
      border: Border.all(color: color.withValues(alpha: 0.6)),
    ),
    child: Text(text, style: TextStyle(fontSize: 10, color: color)),
  );
}

/// The cards currently overlaid on the pitch (newest slide in).
class OverlayStack extends StatelessWidget {
  const OverlayStack({
    super.key,
    required this.cards,
    required this.lang,
    required this.isFavourite,
    required this.showSource,
  });

  final List<OverlayCard> cards;
  final Lang lang;
  final bool Function(OverlayCard) isFavourite;
  final bool showSource;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final c in cards)
          Padding(
            key: ValueKey(c.id),
            padding: const EdgeInsets.only(bottom: 8),
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: 1),
              duration: const Duration(milliseconds: 350),
              curve: Curves.easeOutCubic,
              builder: (_, v, child) => Opacity(
                opacity: v,
                child: Transform.translate(offset: Offset(40 * (1 - v), 0), child: child),
              ),
              child: CardTile(card: c, lang: lang, favourite: isFavourite(c), showSource: showSource),
            ),
          ),
      ],
    );
  }
}

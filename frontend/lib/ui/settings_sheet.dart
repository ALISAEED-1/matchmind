import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controller.dart';
import '../models.dart';
import '../theme.dart';

void showSettings(BuildContext context) {
  final c = context.read<MatchController>();
  showModalBottomSheet<void>(
    context: context,
    backgroundColor: MM.surface,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (_) => ChangeNotifierProvider.value(value: c, child: const _SettingsSheet()),
  );
}

class _SettingsSheet extends StatelessWidget {
  const _SettingsSheet();

  @override
  Widget build(BuildContext context) {
    final c = context.watch<MatchController>();
    final t = Theme.of(context).textTheme;
    final m = c.meta;
    if (m == null) return const SizedBox(height: 120);
    final club = c.favouriteClub;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Your viewer profile', style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 4),
            Text(
              c.isLive
                  ? 'In live mode the Personalizer agent writes for this profile; changing it restarts the session.'
                  : 'The Personalizer agent already wrote every variant, so changes apply instantly.',
              style: t.bodySmall?.copyWith(color: MM.muted),
            ),
            const SizedBox(height: 20),
            DropdownButtonFormField<String?>(
              value: c.favouriteClubId,
              decoration: const InputDecoration(labelText: 'Favourite club', border: OutlineInputBorder()),
              items: [
                const DropdownMenuItem(value: null, child: Text('No favourite (neutral)')),
                for (final cl in [m.home, m.away]) DropdownMenuItem(value: cl.id, child: Text(cl.name)),
              ],
              onChanged: c.setFavouriteClub,
            ),
            const SizedBox(height: 14),
            DropdownButtonFormField<String?>(
              value: c.favouritePlayerId,
              decoration: InputDecoration(
                labelText: 'Favourite player (used by Player focus)',
                border: const OutlineInputBorder(),
                helperText: club == null ? 'Pick a club first, or choose from both squads' : null,
              ),
              items: [
                const DropdownMenuItem(value: null, child: Text('None')),
                for (final cl in club == null ? [m.home, m.away] : [club])
                  for (final p in cl.players)
                    DropdownMenuItem(value: p.id, child: Text('${p.name}  ·  ${p.position}  ·  ${cl.shortName}')),
              ],
              onChanged: c.setFavouritePlayer,
            ),
            const SizedBox(height: 18),
            Text('Language', style: t.labelLarge),
            const SizedBox(height: 8),
            SegmentedButton<Lang>(
              segments: [for (final l in Lang.values) ButtonSegment(value: l, label: Text(l.label))],
              selected: {c.language},
              onSelectionChanged: (s) => c.setLanguage(s.first),
            ),
            const SizedBox(height: 18),
            Text('Replay speed', style: t.labelLarge),
            const SizedBox(height: 8),
            SegmentedButton<double>(
              segments: [for (final s in MatchController.speeds) ButtonSegment(value: s, label: Text('${s.toInt()}x'))],
              selected: {c.speed},
              onSelectionChanged: (s) => c.setSpeed(s.first),
            ),
          ],
        ),
      ),
    );
  }
}

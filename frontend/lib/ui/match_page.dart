import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controller.dart';
import '../models.dart';
import '../theme.dart';
import 'cards.dart';
import 'debug_drawer.dart';
import 'panels.dart';
import 'pitch_view.dart';
import 'recap_page.dart';
import 'ask_sheet.dart';
import 'settings_sheet.dart';

final _scaffoldKey = GlobalKey<ScaffoldState>();

class MatchPage extends StatelessWidget {
  const MatchPage({super.key});

  @override
  Widget build(BuildContext context) {
    final c = context.watch<MatchController>();
    final t = Theme.of(context).textTheme;

    if (c.error != null && c.meta == null) {
      return Scaffold(
        appBar: AppBar(),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(c.error!, textAlign: TextAlign.center),
                if (c.isLive) ...[
                  const SizedBox(height: 24),
                  FilledButton.icon(
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('Watch the demo instead'),
                    onPressed: () => Navigator.of(context).pushReplacement(
                      MaterialPageRoute<void>(
                        builder: (_) => ChangeNotifierProvider(
                          create: (_) => MatchController.demo(matchId: c.matchId, repo: c.repo)..load(),
                          child: const MatchPage(),
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      );
    }
    if (c.loading || c.meta == null) {
      return Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CircularProgressIndicator(),
              const SizedBox(height: 16),
              Text(
                c.isLive ? 'Connecting to the agent team...' : 'Loading match and agent cards...',
                style: t.bodyMedium?.copyWith(color: MM.muted),
              ),
            ],
          ),
        ),
      );
    }

    if (c.openDrawerOnLoad || c.openRecapOnLoad || c.openAskOnLoad) {
      final drawer = c.openDrawerOnLoad, recap = c.openRecapOnLoad, ask = c.openAskOnLoad;
      c.openDrawerOnLoad = c.openRecapOnLoad = c.openAskOnLoad = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (recap) {
          c.seekTo(c.events.last.ts.toDouble());
          Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => ChangeNotifierProvider.value(value: c, child: const RecapPage()),
            ),
          );
        } else if (drawer) {
          _scaffoldKey.currentState?.openEndDrawer();
        } else if (ask) {
          showAsk(_scaffoldKey.currentContext ?? context);
        }
      });
    }

    return Scaffold(
      key: _scaffoldKey,
      endDrawer: const DebugDrawer(),
      appBar: AppBar(
        title: Row(
          children: [
            const Icon(Icons.sports_soccer, color: MM.primary),
            const SizedBox(width: 8),
            const Text('MatchMind', style: TextStyle(fontWeight: FontWeight.w800)),
            if (c.isLive) ...[const SizedBox(width: 10), _pill('LIVE AGENTS', const Color(0xFFFF5252))],
          ],
        ),
        actions: [
          Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(color: MM.surface, borderRadius: BorderRadius.circular(8)),
              child: Text(
                c.minuteLabel,
                style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800, color: MM.highlight),
              ),
            ),
          ),
          IconButton(
            tooltip: 'Ask MatchMind (GitHub Copilot agent)',
            icon: const Icon(Icons.forum_outlined),
            onPressed: () => showAsk(context),
          ),
          IconButton(tooltip: 'Viewer profile', icon: const Icon(Icons.tune), onPressed: () => showSettings(context)),
          Builder(
            builder: (ctx) => IconButton(
              tooltip: 'Agent handoffs (debug)',
              icon: const Icon(Icons.hub_outlined),
              onPressed: () => Scaffold.of(ctx).openEndDrawer(),
            ),
          ),
          const SizedBox(width: 8),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: MM.primary,
        foregroundColor: Colors.black,
        onPressed: c.togglePlay,
        child: Icon(c.playing ? Icons.pause : Icons.play_arrow),
      ),
      body: LayoutBuilder(
        builder: (context, box) {
          final wide = box.maxWidth >= 1000;
          final main = _MainColumn(c: c, wide: wide);
          if (!wide) return main;
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(flex: 7, child: main),
              SizedBox(width: 380, child: _Feed(c: c)),
            ],
          );
        },
      ),
    );
  }
}

Widget _pill(String text, Color color) => Container(
  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
  decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(6)),
  child: Text(
    text,
    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Colors.white),
  ),
);

class _MainColumn extends StatelessWidget {
  const _MainColumn({required this.c, required this.wide});

  final MatchController c;
  final bool wide;

  @override
  Widget build(BuildContext context) {
    final m = c.meta!;
    final focus = c.audience == Audience.playerFocus ? c.favouritePlayerId : null;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 96),
      children: [
        Scoreboard(c: c),
        const SizedBox(height: 12),
        Center(
          child: SegmentedButton<Audience>(
            segments: [for (final a in Audience.values) ButtonSegment(value: a, label: Text(a.label))],
            selected: {c.audience},
            onSelectionChanged: (s) {
              c.setAudience(s.first);
              if (s.first == Audience.playerFocus && c.favouritePlayerId == null) showSettings(context);
            },
          ),
        ),
        if (c.audience == Audience.playerFocus && c.favouritePlayer != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Center(
              child: Text(
                'Following ${c.favouritePlayer!.name}',
                style: const TextStyle(color: MM.highlight, fontWeight: FontWeight.w700),
              ),
            ),
          ),
        const SizedBox(height: 12),
        // Keep scoreboard, pitch and momentum on one screen on laptops.
        Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).height * 0.5 * 105 / 68),
            child: _pitchWithOverlay(context, m, focus),
          ),
        ),
        const SizedBox(height: 12),
        MomentumChart(c: c),
        if (c.audience == Audience.analyst) ...[const SizedBox(height: 12), StatsPanel(c: c)],
        if (c.finished) ...[
          const SizedBox(height: 16),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: MM.highlight, foregroundColor: Colors.black),
            icon: const Icon(Icons.emoji_events_outlined),
            label: const Text('Full time: read the recap'),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => ChangeNotifierProvider.value(value: c, child: const RecapPage()),
              ),
            ),
          ),
        ],
        if (!c.isLive && !c.finished) ...[
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: () => c.seekTo(c.events.last.ts.toDouble()),
              icon: const Icon(Icons.fast_forward, size: 18),
              label: const Text('Skip to full time'),
            ),
          ),
        ],
        if (!wide) ...[const SizedBox(height: 12), SizedBox(height: 520, child: _Feed(c: c))],
        if (c.error != null) ...[
          const SizedBox(height: 12),
          Text(c.error!, style: const TextStyle(color: Color(0xFFFF5252))),
        ],
      ],
    );
  }
}

extension on _MainColumn {
  Widget _pitchWithOverlay(BuildContext context, MatchMeta m, String? focus) {
    return Stack(
      children: [
        PitchView(events: c.recentEvents, home: m.home.primary, away: m.away.primary, focusPlayerId: focus),
        Positioned(
          top: 12,
          right: 12,
          width: wide ? 380 : 260,
          child: OverlayStack(
            // Narrow screens: one compact card so the pitch stays visible.
            cards: wide ? c.activeCards : c.activeCards.take(1).toList(),
            compact: !wide,
            lang: c.language,
            isFavourite: (card) =>
                c.isFavourite(card.team) || (card.playerId != null && card.playerId == c.favouritePlayerId),
            showSource: wide && c.audience == Audience.analyst,
          ),
        ),
        if (c.clockMs == 0 && !c.playing)
          Positioned.fill(
            child: Center(
              child: FilledButton.icon(
                onPressed: c.play,
                icon: const Icon(Icons.play_arrow),
                label: const Text('Kick off'),
              ),
            ),
          ),
      ],
    );
  }
}

class _Feed extends StatelessWidget {
  const _Feed({required this.c});

  final MatchController c;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final feed = c.feed;
    return Container(
      margin: const EdgeInsets.fromLTRB(0, 4, 16, 16),
      decoration: BoxDecoration(color: MM.surfaceHigh.withValues(alpha: 0.4), borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
            child: Text('MATCH FEED', style: t.labelSmall?.copyWith(color: MM.muted, letterSpacing: 1.2)),
          ),
          Expanded(
            child: feed.isEmpty
                ? Center(
                    child: Text(
                      'Cards appear here as the agents publish them',
                      style: t.bodySmall?.copyWith(color: MM.muted),
                      textAlign: TextAlign.center,
                    ),
                  )
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                    itemCount: feed.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 8),
                    itemBuilder: (_, i) {
                      final card = feed[i];
                      return CardTile(
                        card: card,
                        lang: c.language,
                        compact: true,
                        minute: "${card.matchMinute + 1}'",
                        favourite: c.isFavourite(card.team),
                        showSource: c.audience == Audience.analyst,
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

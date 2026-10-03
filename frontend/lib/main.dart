import 'package:flutter/material.dart';

import 'theme.dart';
import 'ui/home_page.dart';

void main() => runApp(const MatchMindApp());

class MatchMindApp extends StatelessWidget {
  const MatchMindApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MatchMind',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: const HomePage(),
    );
  }
}

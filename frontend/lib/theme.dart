// Dark broadcast theme and typography (Nastaliq for Urdu, Naskh for Arabic).

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'models.dart';

class MM {
  static const background = Color(0xFF0B0F14);
  static const surface = Color(0xFF151B23);
  static const surfaceHigh = Color(0xFF1E2631);
  static const primary = Color(0xFF00E676); // pitch green
  static const highlight = Color(0xFFFFC400); // amber
  static const text = Color(0xFFE6EDF3);
  static const muted = Color(0xFF8B98A9);
  static const pitch = Color(0xFF0E3B24);
  static const pitchLine = Color(0x88E6EDF3);

  static Color cardColor(String type) => switch (type) {
    'insight' => primary,
    'commentary' => const Color(0xFF4FC3F7),
    'milestone' => const Color(0xFFB388FF),
    'recap' => highlight,
    _ => highlight, // stat
  };

  static Color statusColor(String status) => switch (status) {
    'ok' => primary,
    'cached' => const Color(0xFF4FC3F7),
    'retry' => highlight,
    'provider_fallback' => const Color(0xFFFF9100),
    'fallback' => const Color(0xFFFF5252),
    _ => muted, // skipped
  };
}

ThemeData buildTheme() {
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: const ColorScheme.dark(
      primary: MM.primary,
      secondary: MM.highlight,
      surface: MM.surface,
      onPrimary: Colors.black,
      onSurface: MM.text,
    ),
    scaffoldBackgroundColor: MM.background,
  );
  return base.copyWith(
    textTheme: GoogleFonts.interTextTheme(base.textTheme).apply(bodyColor: MM.text, displayColor: MM.text),
    appBarTheme: const AppBarTheme(backgroundColor: MM.background, elevation: 0, centerTitle: false),
    cardTheme: const CardThemeData(color: MM.surface, margin: EdgeInsets.zero),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        visualDensity: VisualDensity.compact,
        backgroundColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? MM.primary : MM.surface,
        ),
        foregroundColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? Colors.black : MM.text,
        ),
      ),
    ),
  );
}

/// Text style for card content in the viewer's language.
TextStyle langStyle(Lang lang, TextStyle base) => switch (lang) {
  Lang.ur => GoogleFonts.notoNastaliqUrdu(textStyle: base, height: 1.9),
  Lang.ar => GoogleFonts.notoNaskhArabic(textStyle: base, height: 1.5),
  Lang.en => base,
};

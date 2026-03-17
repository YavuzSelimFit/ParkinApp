import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppColors {
  static const Color background = Color(0xFF131313); // The primary dark void
  static const Color canvas = background;
  static const Color primary = Color(0xFF00E5FF); // Luminous Cyan
  static const Color primaryContainer = Color(0xFF00E5FF);
  static const Color onPrimaryContainer = Color(0xFF131313);
  static const Color critical = Color(0xFFFF3B30); // Tertiary Warning Red
  static const Color tertiary_container = critical;
  
  // Tonal Layering (Surface Containers)
  static const Color surfaceLow = Color(0xFF1C1B1B);
  static const Color surfaceMedium = Color(0xFF252525);
  static const Color surfaceHigh = Color(0xFF353534);
  
  static const Color primaryText = Color(0xFFBAC9CC); // on_surface_variant for eye strain reduction
  static const Color secondaryText = Color(0xFF7E8C8F);
  static const Color accentGlow = Color(0x1000E5FF); // Cyan-tinted ambient glow
  
  // Available/Success Green (for the Bento Slots)
  static const Color success = Color(0xFF00A86B);
  static const Color successGlow = Color(0x2000A86B);
}

class AppTheme {
  static ThemeData get kineticCockpit {
    return ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: const Color(0xFFFCFDFD),
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.primary,
        primary: AppColors.primary,
        surface: Colors.white,
      ),
      textTheme: TextTheme(
        headlineLarge: GoogleFonts.plusJakartaSans(
          fontWeight: FontWeight.w800,
          color: Colors.black,
        ),
        headlineMedium: GoogleFonts.spaceGrotesk(
          fontWeight: FontWeight.w700,
          color: AppColors.primary,
        ),
        bodyMedium: GoogleFonts.inter(
          color: Colors.black87,
        ),
        labelLarge: GoogleFonts.spaceGrotesk(
          fontWeight: FontWeight.bold,
          letterSpacing: 1,
        ),
      ),
    );
  }
}

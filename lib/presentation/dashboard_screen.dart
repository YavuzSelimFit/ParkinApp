import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../features/telemetry/presentation/telemetry_header.dart';
import '../features/scanner/presentation/qr_scanner_overlay.dart';
import '../features/navigation/application/navigation_providers.dart';
import '../core/models/parking_space.dart';
import '../core/theme/app_theme.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> with SingleTickerProviderStateMixin {
  late AnimationController _floatController;

  @override
  void initState() {
    super.initState();
    _floatController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _floatController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final slots = ref.watch(parkingSlotsProvider);
    
    return Scaffold(
      body: Stack(
        children: [
          // Background Gradient
          Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Color(0xFFFCFDFD), Color(0xFFF1FDF6)],
              ),
            ),
          ),

          SafeArea(
            child: Column(
              children: [
                const TelemetryHeader(
                  speed: 0.0,
                  battery: 85,
                  signal: 94,
                ),
                
                // Professional Asset-Based Isometric Scene
                Expanded(
                  child: buildProfessionalParkingLayout(slots),
                ),
              ],
            ),
          ),

          // Bottom Action Shell (Glassmorphic)
          Positioned(
            left: 0,
            right: 0,
            bottom: 32,
            child: Center(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(32),
                child: Container(
                  width: math.min(MediaQuery.of(context).size.width - 48, 400),
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: const Color(0xEE1A1A1A), // Dark glass
                    borderRadius: BorderRadius.circular(32),
                    border: Border.all(color: const Color(0x0DFFFFFF)),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: _NavButtonV2(
                          label: 'SUMMON',
                          icon: Icons.rocket_launch,
                          color: const Color(0xFF00E5FF),
                          textColor: Colors.black,
                          onPressed: () => _summonVehicle(),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _NavButtonV2(
                          label: 'STOP',
                          icon: Icons.report_problem,
                          color: const Color(0x0DFFFFFF),
                          textColor: const Color(0xFFFF453A),
                          onPressed: () => ref.read(hardwareServiceProvider).sendEmergencyStop(),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget buildProfessionalParkingLayout(List<ParkingSlot> slots) {
    // Magic Matrix4 for isometric perspective
    Matrix4 isometricMatrix = Matrix4.identity()
      ..setEntry(3, 2, 0.001) // Perspective depth
      ..rotateX(-0.5) // Tilt back
      ..rotateZ(0.7); // Rotate scene

    return Center(
      child: Transform(
        transform: isometricMatrix,
        alignment: FractionalOffset.center,
        child: Stack(
          alignment: Alignment.center,
          children: [
            // LAYER 1: BASE TEXTURE
            Image.asset(
              'assets/images/base_texture.png',
              width: 800,
              fit: BoxFit.cover,
            ),

            // LAYER 2: PARK SLOTS (2x5 Grid)
            SizedBox(
              width: 500,
              height: 800,
              child: GridView.count(
                padding: const EdgeInsets.symmetric(vertical: 40),
                crossAxisCount: 2,
                mainAxisSpacing: 30,
                crossAxisSpacing: 30,
                childAspectRatio: 0.7,
                physics: const NeverScrollableScrollPhysics(),
                children: List.generate(slots.length, (index) {
                  return ParkingSlotBuilder(
                    index: index,
                    onTap: () {
                      if (slots[index].isOccupied) {
                        _sendLocation(slots[index].space!);
                      } else {
                        _learnNewSlot(index);
                      }
                    },
                  );
                }),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _learnNewSlot(int index) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => QRScannerOverlay(
          onResult: (qrValue) {
            // SADECE QR OKUTULDUĞUNDA ÇAĞRILACAK (Hologramı başlatır)
            ref.read(parkingSlotsProvider.notifier).assignQrToSlot(index, qrValue);
            Navigator.pop(context);
          },
        ),
      ),
    );
  }

  void _summonVehicle() {
    _sendLocation(const ParkingSpace(
      id: 'summon',
      label: 'HOME',
      qrValue: 'ORIGIN_00',
      coordinates: [0, 0],
    ));
  }

  void _sendLocation(ParkingSpace space) {
    if (!ref.read(isConnectedProvider)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('VEHICLE OFFLINE'),
          backgroundColor: Colors.black,
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }
    ref.read(hardwareServiceProvider).sendParkCommand(space);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('SENDING TARGET: ${space.label.toUpperCase()}'),
        backgroundColor: AppColors.primary,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }
}

class ParkingSlotBuilder extends ConsumerWidget {
  final int index;
  final VoidCallback onTap;

  const ParkingSlotBuilder({
    super.key,
    required this.index,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // 1. Durumları Oku
    final slotData = ref.watch(parkingSlotsProvider)[index];
    final isOccupied = slotData.isOccupied; // Araç orada mı?
    final hasQrAssigned = slotData.hasQrAssigned; // QR Atandı mı?

    return GestureDetector(
      onTap: onTap,
      child: Container(
        color: Colors.transparent, // Ensure hit test works
        child: Stack(
          alignment: Alignment.center,
          clipBehavior: Clip.none,
          children: [
            // LAYER 1: NEON SLOT LINES
            Image.asset(
              'assets/images/slot_line.png',
              width: 180,
            ),

            // LAYER 2: STATUS INDICATORS (Hologram & Car)
            
            // Hologram QR (Visible when QR is assigned and car is not there)
            if (hasQrAssigned && !isOccupied)
              Positioned(
                bottom: 20,
                child: HoveringHologram(
                  child: Opacity(
                    opacity: 0.8,
                    child: Image.asset(
                      'assets/images/hologram_qr.png',
                      width: 100,
                    ),
                  ),
                ),
              ),

            // Cyberpunk Toy Car (Visible when occupied)
            if (isOccupied)
              Positioned(
                top: -10,
                child: Image.asset(
                  'assets/images/toy_car.png',
                  width: 140,
                ),
              )
            else if (!hasQrAssigned)
              // Floating "+" icon for empty slots (only if no QR assigned)
              const HoveringHologram(
                child: _AddIcon(),
              ),

            // LAYER 3: PERSPECTIVE LABEL
            Positioned(
              left: 10,
              bottom: -10,
              child: Transform(
                transform: Matrix4.identity()
                  ..rotateZ(-0.7)
                  ..rotateX(1.1),
                child: Text(
                  slotData.label,
                  style: GoogleFonts.spaceGrotesk(
                    color: hasQrAssigned ? const Color(0xFF00E5FF) : Colors.white.withValues(alpha: 0.5),
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                    shadows: hasQrAssigned 
                      ? [const BoxShadow(color: Color(0xFF00E5FF), blurRadius: 8)] 
                      : [],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AddIcon extends StatelessWidget {
  const _AddIcon();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: [Color(0xFF006D43), Color(0xFF00A86B)],
        ),
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: Color(0x3300A86B),
            blurRadius: 10,
            spreadRadius: 2,
          )
        ],
      ),
      child: const Icon(Icons.add, color: Colors.white, size: 16),
    );
  }
}

class HoveringHologram extends StatefulWidget {
  final Widget child;
  const HoveringHologram({super.key, required this.child});

  @override
  State<HoveringHologram> createState() => _HoveringHologramState();
}

class _HoveringHologramState extends State<HoveringHologram> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(seconds: 2),
      vsync: this,
    )..repeat(reverse: true);

    _animation = Tween<double>(begin: 0, end: -15).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOutSine),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _animation,
      builder: (context, child) {
        return Transform.translate(
          offset: Offset(0, _animation.value),
          child: child,
        );
      },
      child: widget.child,
    );
  }
}

class _NavButtonV2 extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final Color textColor;
  final VoidCallback onPressed;

  const _NavButtonV2({
    required this.label,
    required this.icon,
    required this.color,
    required this.textColor,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onPressed,
      borderRadius: BorderRadius.circular(24),
      child: Container(
        height: 56,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(24),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: textColor, size: 18),
            const SizedBox(width: 8),
            Text(
              label,
              style: GoogleFonts.spaceGrotesk(
                color: textColor,
                fontWeight: FontWeight.bold,
                fontSize: 13,
                letterSpacing: 1.2,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

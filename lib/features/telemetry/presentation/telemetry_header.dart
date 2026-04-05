import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../navigation/application/navigation_providers.dart';

class TelemetryHeader extends StatelessWidget {
  final double speed;
  final int battery;
  final int signal;

  const TelemetryHeader({
    super.key,
    required this.speed,
    required this.battery,
    required this.signal,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(
                speed.toStringAsFixed(2),
                style: Theme.of(context).textTheme.displayLarge,
              ),
              const SizedBox(width: 8),
              Text(
                'M/S',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  letterSpacing: 2,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              _TelemetryCapsule(
                icon: Icons.battery_charging_full,
                label: '$battery MIN',
              ),
              const SizedBox(width: 12),
              _TelemetryCapsule(
                icon: Icons.bluetooth_connected,
                label: '$signal%',
              ),
              const Spacer(),
              StatusIndicator(),
            ],
          ),
        ],
      ),
    );
  }
}

class StatusIndicator extends ConsumerWidget {
  const StatusIndicator({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isConnected = ref.watch(isConnectedProvider);
    return GestureDetector(
      onTap: () async {
        if (!isConnected) {
          final hasPerms = await ref.read(permissionServiceProvider).requestBluetoothPermissions();
          if (hasPerms) {
            ref.read(hardwareServiceProvider).startScanning();
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('RPI TARANIYOR...')),
              );
            }
          }
        }
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isConnected ? const Color(0x1A00E5FF) : AppColors.primary,
          borderRadius: BorderRadius.circular(12),
          boxShadow: isConnected ? [] : [
            BoxShadow(
              color: AppColors.primary.withValues(alpha: 0.3),
              blurRadius: 12,
              offset: const Offset(0, 4),
            )
          ],
          border: Border.all(
            color: isConnected ? const Color(0x4D00E5FF) : AppColors.primary,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isConnected ? Icons.bluetooth_connected : Icons.bluetooth,
              size: 14,
              color: isConnected ? AppColors.primary : Colors.white,
            ),
            const SizedBox(width: 8),
            Text(
              isConnected ? 'BAĞLI' : 'CİHAZ BAĞLA',
              style: GoogleFonts.spaceGrotesk(
                color: isConnected ? AppColors.primary : Colors.white,
                fontSize: 11,
                fontWeight: FontWeight.w900,
                letterSpacing: 1,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TelemetryCapsule extends StatelessWidget {
  final IconData icon;
  final String label;

  const _TelemetryCapsule({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFFF1FDF6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFA7F3D0)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: AppColors.primary),
          const SizedBox(width: 6),
          Text(
            label,
            style: GoogleFonts.inter(
              color: AppColors.primary,
              fontWeight: FontWeight.w700,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }
}

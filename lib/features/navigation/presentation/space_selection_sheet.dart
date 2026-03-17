import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/navigation_providers.dart';
import '../../../core/models/vehicle_state.dart';
import '../../../core/models/parking_space.dart';
import '../../../core/theme/app_theme.dart';

class SpaceSelectionSheet extends ConsumerWidget {
  const SpaceSelectionSheet({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final slots = ref.watch(parkingSlotsProvider);
    final spaces = slots.where((s) => s.isOccupied).map((s) => s.space!).toList();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
      decoration: const BoxDecoration(
        color: AppColors.surfaceLow,
        borderRadius: BorderRadius.vertical(top: Radius.circular(48)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'PARK ALANI SEÇİN',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 32),
          ...spaces.map((space) => _SpaceItem(space: space)),
          const SizedBox(height: 16),
          TextButton(
            onPressed: () => Navigator.pop(context),
            style: TextButton.styleFrom(
              foregroundColor: AppColors.secondaryText,
              padding: const EdgeInsets.symmetric(vertical: 20),
            ),
            child: const Text(
              'İPTAL',
              style: TextStyle(fontWeight: FontWeight.w700, letterSpacing: 1.5),
            ),
          ),
        ],
      ),
    );
  }
}

class _SpaceItem extends ConsumerWidget {
  final ParkingSpace space;

  const _SpaceItem({required this.space});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      child: ElevatedButton(
        onPressed: () {
          ref.read(selectedParkingSpaceProvider.notifier).state = space;
          ref.read(vehicleStatusProvider.notifier).state = VehicleStatus.parkingInProgress;
          ref.read(hardwareServiceProvider).sendParkCommand(space);
          Navigator.pop(context);
        },
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.surfaceMedium,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 24),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
          ),
          elevation: 0,
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              space.label.toUpperCase(),
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, letterSpacing: 1),
            ),
            const Icon(Icons.arrow_forward_ios, size: 16, color: AppColors.primary),
          ],
        ),
      ),
    );
  }
}

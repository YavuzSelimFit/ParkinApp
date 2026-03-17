import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/models/vehicle_state.dart';
import '../../../core/models/parking_space.dart';
import '../../../services/hardware_communication_service.dart';

import '../../../core/services/permission_service.dart';

final hardwareServiceProvider = Provider((ref) => HardwareCommunicationService());
final permissionServiceProvider = Provider((ref) => PermissionService());

final vehicleStatusProvider = StateProvider<VehicleStatus>((ref) => VehicleStatus.disconnected);

final isConnectedProvider = Provider<bool>((ref) {
  final status = ref.watch(vehicleStatusProvider);
  return status != VehicleStatus.disconnected;
});

// Listener setup (this would usually be in a more global place or initState)
final vehicleStatusListenerProvider = Provider((ref) {
  final service = ref.watch(hardwareServiceProvider);
  service.statusStream.listen((status) {
    ref.read(vehicleStatusProvider.notifier).state = status;
  });
});
class ParkingSlot {
  final String label;
  final ParkingSpace? space;
  const ParkingSlot({required this.label, this.space});

  bool get isOccupied => space != null;

  ParkingSlot copyWith({ParkingSpace? space}) {
    return ParkingSlot(label: label, space: space ?? this.space);
  }
}

class ParkingSlotsNotifier extends StateNotifier<List<ParkingSlot>> {
  ParkingSlotsNotifier() : super([
    const ParkingSlot(label: 'A1'),
    const ParkingSlot(label: 'A2'),
    const ParkingSlot(label: 'B1'),
    const ParkingSlot(label: 'B2'),
    const ParkingSlot(label: 'C1'),
    const ParkingSlot(label: 'C2'),
    const ParkingSlot(label: 'D1'),
    const ParkingSlot(label: 'D2'),
    const ParkingSlot(label: 'E1'),
    const ParkingSlot(label: 'E2'),
  ]);

  void updateSlot(int index, String qrValue) {
    if (index < 0 || index >= state.length) return;
    
    final currentSlot = state[index];
    final newSpace = ParkingSpace(
      id: 'slot_${currentSlot.label}',
      label: currentSlot.label,
      qrValue: qrValue,
      coordinates: [0, 0],
    );

    state = [
      for (int i = 0; i < state.length; i++)
        if (i == index) currentSlot.copyWith(space: newSpace) else state[i],
    ];
  }

  void clearSlot(int index) {
    if (index < 0 || index >= state.length) return;
    state = [
      for (int i = 0; i < state.length; i++)
        if (i == index) ParkingSlot(label: state[i].label) else state[i],
    ];
  }
}

final parkingSlotsProvider = StateNotifierProvider<ParkingSlotsNotifier, List<ParkingSlot>>((ref) {
  return ParkingSlotsNotifier();
});

final selectedParkingSpaceProvider = StateProvider<ParkingSpace?>((ref) => null);

// Telemetry stream provider
final telemetryStreamProvider = StreamProvider<TelemetryData>((ref) {
  // Mocking the stream for now - in production this would connect to BLE characteristics
  return Stream.periodic(const Duration(milliseconds: 200), (i) {
    return TelemetryData(
      speed: (i % 5) * 0.1,
      batteryLevel: 15 - (i ~/ 100),
      signalStrength: 85 + (i % 10),
    );
  });
});

final telemetryProvider = Provider<TelemetryData>((ref) {
  return ref.watch(telemetryStreamProvider).asData?.value ?? TelemetryData.initial();
});

enum VehicleStatus {
  disconnected,
  idle,
  scanningQR,
  selectingSpace,
  parkingInProgress,
  parkedSuccessfully,
  summoning,
  emergencyHalted,
}

class TelemetryData {
  final double speed;
  final int batteryLevel;
  final int signalStrength;

  TelemetryData({
    required this.speed,
    required this.batteryLevel,
    required this.signalStrength,
  });

  factory TelemetryData.initial() => TelemetryData(
        speed: 0.0,
        batteryLevel: 0,
        signalStrength: 0,
      );
}

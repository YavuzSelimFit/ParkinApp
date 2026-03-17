class ParkingSpace {
  final String id;
  final String label;
  final String qrValue;
  final List<int> coordinates; // [x, y] or similar byte-serializable format

  const ParkingSpace({
    required this.id,
    required this.label,
    required this.qrValue,
    required this.coordinates,
  });
}

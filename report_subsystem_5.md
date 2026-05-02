# Subsystem 5: Mobile Application

The mobile application serves as the primary human-machine interface (HMI) for the Intelligent Parking System. Developed using the Flutter framework and Dart programming language, the application provides a cross-platform, responsive, and intuitive dashboard. It is responsible for orchestrating vehicle navigation tasks, parsing complex physical environments into digital commands, and maintaining real-time telemetry with the central hardware controller.

### 1. Computer Vision & Spatial Mapping (ArUco Integration)
A critical feature of the mobile application is its integration with professional-grade computer vision libraries, specifically `opencv_dart` utilizing Foreign Function Interface (FFI) for high-performance memory management. The application actively captures raw BGRA/Grayscale frames from the device's camera module to detect and decode **ArUco Markers (Predefined Dictionary: `DICT_6X6_250`)**. 
By scanning these markers, the system binds dynamic physical parking coordinates to a digital grid index. This eliminates the need for hardcoded paths, allowing the system to deploy mapping anchors seamlessly across varied environments.

### 2. State Management & Logic Handling
To ensure robust and predictable state transitions, the application employs `Riverpod` for reactive state management. The digital twin of the parking lot is maintained via a `ParkingSlotsNotifier`, which tracks:
- Unassigned slots (Empty)
- Slots pending vehicle arrival (ArUco assigned but empty)
- Occupied slots (Vehicle successfully parked)
This isolated business logic ensures the user interface remains synchronized with the physical reality of the parking lot without suffering from UI-blocking operations.

### 3. Bluetooth Low Energy (BLE) Telemetry & Command Protocol
The communication layer between the mobile subsystem and the vehicle's primary processing unit (Raspberry Pi 5) is established via Bluetooth Low Energy (BLE) utilizing the `flutter_reactive_ble` package. 
* **Auto-Discovery:** The app is configured with specific discovery protocols to scan and latch onto the hardware node (e.g., broadcasting as `RPi`).
* **Command Transmission:** Upon selecting a valid, marker-assigned parking slot from the UI, the application encodes the destination's ArUco ID into a UTF-8 byte array and writes it to a predefined GATT Characteristic.
* **Hardware Confirmation:** The app maintains a continuous subscription to the hardware's notification channel. Once the vehicle executes the maneuver, the Raspberry Pi transmits a success parity string back to the app, triggering an automatic UI update securely mapping the vehicle to the slot.

### 4. User Interface Architecture
The graphical user interface follows a modern, dark-themed aesthetic designed for minimal cognitive load. Key components include:
* **Interactive Dashboard Grid:** A matrix displaying real-time slot availability with dynamic functional buttons (like clear slots or trigger park action).
* **Telemetry Header:** Provides live feedback on BLE connection status and allows fallback manual connection triggers.
* **Safety Context:** Contains high-priority overrides, ensuring immediate transmission processes can be managed smoothly. 

This architecture guarantees that the mobile app is not merely a remote controller, but an active, intelligent node capable of vision processing and bidirectional telemetry orchestration.

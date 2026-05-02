import asyncio
from bless import (
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions
)
import platform

# Bizim Flutter uygulamasındaki UUID'ler
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
SERVER_NAME = "RPi_Park_Server" # Flutter uygulamasında 'rpi' geçtiği için telefonda bulacaktır

async def run():
    print("BLE Sunucusu başlatılıyor...")
    
    server = BlessServer(name=SERVER_NAME)
    server.read_request_func = read_request
    server.write_request_func = write_request

    await server.add_new_service(SERVICE_UUID)

    char_flags = (
        GATTCharacteristicProperties.read |
        GATTCharacteristicProperties.write |
        GATTCharacteristicProperties.notify
    )
    permissions = (
        GATTAttributePermissions.readable |
        GATTAttributePermissions.writeable
    )
    
    await server.add_new_characteristic(
        SERVICE_UUID,
        CHAR_UUID,
        char_flags,
        None,
        permissions
    )

    print("BLE başlatıldı. Uygulamadan 'CİHAZ BAĞLA'ya basarak tarayabilirsiniz.")
    
    await server.start()
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Kapatılıyor...")
        await server.stop()

def read_request(characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
    return characteristic.value

def write_request(characteristic: BlessGATTCharacteristic, value: bytes, **kwargs):
    # Telefondan gönderilen veri (örneğin "A1") buraya düşer.
    try:
        gelen_veri = value.decode('utf-8')
        print(f"\n[🚀 YENİ VERİ ALINDI] Telefondan gelen komut: {gelen_veri}")
        
    except Exception as e:
        print(f"Veri okunurken hata: {e}")
        
    characteristic.value = value

if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run())

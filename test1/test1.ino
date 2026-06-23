#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Wire.h>

// --- HARDWARE PINS ---
const int PIN_BUZZER = 3;
const int PIN_BUTTON = 4;
const int I2C_SDA = 8;
const int I2C_SCL = 9;

// --- BLUETOOTH UUIDS ---
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLEServer* pServer = NULL;
BLECharacteristic* pCharacteristic = NULL;
bool deviceConnected = false;

// --- GLOBAL ACCELERATION VALUES ---
float ax = 0.0;
float ay = 0.0;
float az = 0.0;
float gx = 0.0;
float gy = 0.0;
float gz = 0.0;
// --- FALL DETECTION STATE MACHINE ---
enum SystemState { NORM, DROP, IMPT, ALRM, SOS };
SystemState currentState = NORM;

unsigned long dropTime = 0;
unsigned long alarmStartTime = 0;
const int PRE_ALARM_DURATION = 10000; // 10 seconds

// --- BLE CALLBACKS ---
class MyServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
        deviceConnected = true;
    }

    void onDisconnect(BLEServer* pServer) {
        deviceConnected = false;
        BLEDevice::startAdvertising();
    }
};

// --- READ MPU-9250 ACCELEROMETER ---
float readIMU() {

    // Read all 14 bytes:
    // Accel(6) + Temp(2) + Gyro(6)

    Wire.beginTransmission(0x68);
    Wire.write(0x3B);
    Wire.endTransmission(false);

    Wire.requestFrom(0x68, 14, true);

    if (Wire.available() < 14) {
        return 0.0;
    }

    int16_t axRaw = (Wire.read() << 8) | Wire.read();
    int16_t ayRaw = (Wire.read() << 8) | Wire.read();
    int16_t azRaw = (Wire.read() << 8) | Wire.read();

    Wire.read();
    Wire.read();

    int16_t gxRaw = (Wire.read() << 8) | Wire.read();
    int16_t gyRaw = (Wire.read() << 8) | Wire.read();
    int16_t gzRaw = (Wire.read() << 8) | Wire.read();

    // Accelerometer ±2g
    ax = axRaw / 16384.0;
    ay = ayRaw / 16384.0;
    az = azRaw / 16384.0;

    // Gyroscope ±250 deg/s
    gx = gxRaw / 131.0;
    gy = gyRaw / 131.0;
    gz = gzRaw / 131.0;

    float gForce = sqrt(
        ax * ax +
        ay * ay +
        az * az
    );

    return gForce;
}

void setup() {

    Serial.begin(115200);
    delay(1000);

    pinMode(PIN_BUZZER, OUTPUT);
    pinMode(PIN_BUTTON, INPUT_PULLUP);

    // Start I2C
    Wire.begin(I2C_SDA, I2C_SCL);

    // Wake up MPU-9250 / MPU-6050
    Wire.beginTransmission(0x68);
    Wire.write(0x6B);
    Wire.write(0x00);
    Wire.endTransmission(true);

    // Test sensor connection
    Wire.beginTransmission(0x68);
    byte error = Wire.endTransmission();

    if (error == 0) {
        Serial.println("MPU Connected Successfully!");
    } else {
        Serial.println("MPU NOT FOUND!");
    }

    // --- BLE SETUP ---
    BLEDevice::init("FALL_ALARM_C3");

    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new MyServerCallbacks());

    BLEService *pService = pServer->createService(SERVICE_UUID);

    pCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_WRITE |
        BLECharacteristic::PROPERTY_NOTIFY |
        BLECharacteristic::PROPERTY_INDICATE
    );

    pCharacteristic->addDescriptor(new BLE2902());

    pService->start();

    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    BLEDevice::startAdvertising();

    Serial.println("BLE Advertising Started");

    // Startup beep
    digitalWrite(PIN_BUZZER, HIGH);

    for (int i = 0; i < 2; i++) {
        digitalWrite(PIN_BUZZER, LOW);
        delay(100);
        digitalWrite(PIN_BUZZER, HIGH);
        delay(100);
    }
}

void loop() {

    float gForce = readIMU();

    // --- FALL DETECTION STATE MACHINE ---

    if (currentState == NORM) {

        if (gForce < 0.4) {
            currentState = DROP;
            dropTime = millis();
        }

    } else if (currentState == DROP) {

        if (millis() - dropTime > 1000) {
            currentState = NORM;
        }
        else if (gForce > 2.5) {
            currentState = IMPT;
        }

    } else if (currentState == IMPT) {

        currentState = ALRM;
        alarmStartTime = millis();

    } else if (currentState == ALRM) {

        if (millis() - alarmStartTime > PRE_ALARM_DURATION) {
            currentState = SOS;
        }
    }

    // --- BUTTON RESET ---
    if (digitalRead(PIN_BUTTON) == LOW) {

        currentState = NORM;
        digitalWrite(PIN_BUZZER, HIGH);

        Serial.println("ALARM CANCELLED");

        delay(200);
    }

    // --- BUZZER CONTROL ---
    if (currentState == ALRM) {

        digitalWrite(PIN_BUZZER, (millis() / 500) % 2);

    } else if (currentState == SOS) {

        digitalWrite(PIN_BUZZER, LOW);

    } else {

        digitalWrite(PIN_BUZZER, HIGH);
    }

    // --- STATE STRING ---
    const char* stateStr = "NORM";

    if (currentState == DROP) stateStr = "DROP";
    if (currentState == IMPT) stateStr = "IMPT";
    if (currentState == ALRM) stateStr = "ALRM";
    if (currentState == SOS)  stateStr = "SOS";

    // --- SERIAL MONITOR OUTPUT ---
    Serial.print("State: ");
    Serial.print(stateStr);

    Serial.print(" | X: ");
    Serial.print(ax, 3);

    Serial.print(" | Y: ");
    Serial.print(ay, 3);

    Serial.print(" | Z: ");
    Serial.print(az, 3);

    Serial.print(" | GX: ");
    Serial.print(gx, 2);

    Serial.print(" | GY: ");
    Serial.print(gy, 2);

    Serial.print(" | GZ: ");
    Serial.print(gz, 2);

    Serial.print(" | G: ");
    Serial.println(gForce, 3);

    // --- BLE TRANSMISSION ---
    if (deviceConnected) {

        char txString[64];

        if (currentState == SOS) {
            sprintf(txString, "*** SOS ALARM ***");
        }
        else {
            sprintf(
            txString,
            "%.3f,%.3f,%.3f,%.3f,%.3f,%.3f",
            ax,
            ay,
            az,
            gx,
            gy,
            gz
        );
        }

        pCharacteristic->setValue(txString);
        pCharacteristic->notify();
    }

    delay(50);
}
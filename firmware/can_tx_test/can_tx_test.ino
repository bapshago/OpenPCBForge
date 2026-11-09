// CAN transmitter test for the bench monitor (ESP32 + WCMCU-230). No CAN
// controller: it just holds the transceiver's input low for 5 s, then high for
// 5 s, so a meter can check that the chip drives the bus.
//
// Measure with a multimeter (DC volts) while the serial monitor (115200) says:
//   "TX LOW  (dominant)":  SN65HVD230 pin 1 ~0 V; CANH to CANL ~1.5-2.5 V
//   "TX HIGH (recessive)": pin 1 ~3.3 V;        CANH to CANL ~0 V
// If pin 1 goes low but CANH-CANL stays ~0 V, the transceiver isn't driving.
// The signal module will log CAN errors during the test; that's harmless.

const int TX_PIN = 5;   // the GPIO wired to WCMCU-230 CTX (5 or 21)

void setup() {
  Serial.begin(115200);
  pinMode(TX_PIN, OUTPUT);
}

void loop() {
  digitalWrite(TX_PIN, LOW);
  Serial.printf("GPIO%d TX LOW  (dominant): CANH-CANL should read ~2 V\n", TX_PIN);
  delay(5000);
  digitalWrite(TX_PIN, HIGH);
  Serial.printf("GPIO%d TX HIGH (recessive): CANH-CANL should read ~0 V\n", TX_PIN);
  delay(5000);
}

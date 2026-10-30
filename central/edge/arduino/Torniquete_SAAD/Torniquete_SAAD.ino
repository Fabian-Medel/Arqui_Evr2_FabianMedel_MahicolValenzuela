// SAAD-Campus: torniquete de maqueta (Arduino Uno/R4 + servo SG90).
// El Arduino es un actuador esclavo: no decide accesos, solo obedece al nodo por USB a 9600 baudios.
//   Recibe  OPEN:<event_id>  ->  responde ACK:<event_id>, abre, espera y cierra.
//   Recibe  PING             ->  responde PONG.
// El ACK confirma que el controlador recibio la orden, no el movimiento mecanico.
#include <Servo.h>

const int SERVO_PIN = 9;
const int CLOSED_ANGLE = 0;
const int OPEN_ANGLE = 90;
const unsigned long OPEN_MS = 3000;
const unsigned int MAX_LINE = 80;

Servo gate;
String line;

void setup() {
  Serial.begin(9600);
  gate.attach(SERVO_PIN);
  gate.write(CLOSED_ANGLE);
}

void handle(const String &command) {
  if (command.startsWith("OPEN:")) {
    Serial.print("ACK:");
    Serial.println(command.substring(5));
    Serial.flush();
    gate.write(OPEN_ANGLE);
    delay(OPEN_MS);
    gate.write(CLOSED_ANGLE);
  } else if (command == "PING") {
    Serial.println("PONG");
  } else {
    Serial.println("ERR");
  }
}

void loop() {
  while (Serial.available() > 0) {
    char symbol = Serial.read();
    if (symbol == '\n') {
      line.trim();
      handle(line);
      line = "";
    } else if (line.length() < MAX_LINE) {
      line += symbol;
    }
  }
}

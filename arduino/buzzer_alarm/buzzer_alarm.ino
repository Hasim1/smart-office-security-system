int buzzerPin = 11; // تم التعديل إلى المنفذ 11
char incomingData;

void setup() {
  Serial.begin(9600);
  pinMode(buzzerPin, OUTPUT);
}

void loop() {
  if (Serial.available() > 0) {
    incomingData = Serial.read(); 
    
    if (incomingData == '1') {
      digitalWrite(buzzerPin, HIGH); // تشغيل الإنذار على المنفذ 11
    } 
    else if (incomingData == '0') {
      digitalWrite(buzzerPin, LOW);  // إطفاء الإنذار
    }
  }
}
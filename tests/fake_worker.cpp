#include <QtCore>
#include <iostream>
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    std::string line; std::getline(std::cin, line);
    const auto request = QJsonDocument::fromJson(QByteArray::fromStdString(line)).object();
    auto mode = request["mode"].toString();
    if (mode == "missing") return 0;
    if (mode == "invalid") { std::cout << "not json\n"; return 0; }
    if (mode == "burst") for (int i = 0; i < 10000; ++i) std::cout << "{\"event\":\"progress\"}\n";
    const auto event = mode == "password" ? QJsonObject{{"event", "error"}, {"code", "password_required"}, {"message", request["password"]}}
        : QJsonObject{{"event", "complete"}, {"output_committed", true}, {"output", "example"}};
    std::cout << QJsonDocument(event).toJson(QJsonDocument::Compact).constData() << '\n';
    if (mode == "duplicate") std::cout << QJsonDocument(event).toJson(QJsonDocument::Compact).constData() << '\n';
    return mode == "nonzero" || mode == "password" ? 1 : 0;
}

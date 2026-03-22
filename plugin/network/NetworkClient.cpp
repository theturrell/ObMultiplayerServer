#include "NetworkClient.h"

#include <chrono>
#include <cstring>
#include <sstream>

namespace pseudo_onblivion {

namespace {

std::int64_t NowMs() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count();
}

}  // namespace

NetworkClient::NetworkClient()
    : socket_(INVALID_SOCKET), connected_(false), winsock_started_(false) {}

NetworkClient::~NetworkClient() {
    Disconnect();
}

NetworkClient::NetworkClient(NetworkClient&& other) noexcept
    : socket_(other.socket_),
      connected_(other.connected_.load()),
      winsock_started_(other.winsock_started_) {
    other.socket_ = INVALID_SOCKET;
    other.connected_ = false;
    other.winsock_started_ = false;
}

NetworkClient& NetworkClient::operator=(NetworkClient&& other) noexcept {
    if (this == &other) {
        return *this;
    }

    Disconnect();
    socket_ = other.socket_;
    connected_ = other.connected_.load();
    winsock_started_ = other.winsock_started_;

    other.socket_ = INVALID_SOCKET;
    other.connected_ = false;
    other.winsock_started_ = false;
    return *this;
}

bool NetworkClient::StartWinsock() {
    if (winsock_started_) {
        return true;
    }

    WSADATA wsa_data{};
    if (WSAStartup(MAKEWORD(2, 2), &wsa_data) != 0) {
        return false;
    }

    winsock_started_ = true;
    return true;
}

bool NetworkClient::Connect(
    const std::string& host,
    unsigned short port,
    const std::string& room,
    const std::string& sender,
    const std::string& character_name,
    bool host_authority,
    const std::string& token
) {
    if (!StartWinsock()) {
        return false;
    }

    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    addrinfo* result = nullptr;
    const std::string port_str = std::to_string(port);
    if (getaddrinfo(host.c_str(), port_str.c_str(), &hints, &result) != 0) {
        return false;
    }

    socket_ = ::socket(result->ai_family, result->ai_socktype, result->ai_protocol);
    if (socket_ == INVALID_SOCKET) {
        freeaddrinfo(result);
        return false;
    }

    if (::connect(socket_, result->ai_addr, static_cast<int>(result->ai_addrlen)) == SOCKET_ERROR) {
        freeaddrinfo(result);
        CloseSocket();
        return false;
    }
    freeaddrinfo(result);

    connected_ = true;
    return SendJson(BuildHelloJson(room, sender, character_name, host_authority, token));
}

bool NetworkClient::SendJson(const std::string& json) {
    if (!connected_) {
        return false;
    }

    const std::string framed = json + "\n";
    std::lock_guard<std::mutex> lock(send_mutex_);
    const int sent = send(socket_, framed.c_str(), static_cast<int>(framed.size()), 0);
    if (sent == SOCKET_ERROR) {
        connected_ = false;
        CloseSocket();
        return false;
    }

    return true;
}

std::string NetworkClient::ReceiveLine() {
    if (!connected_) {
        return {};
    }

    std::lock_guard<std::mutex> lock(receive_mutex_);
    std::string line;
    char ch = '\0';
    while (connected_) {
        const int received = recv(socket_, &ch, 1, 0);
        if (received <= 0) {
            connected_ = false;
            CloseSocket();
            return {};
        }
        if (ch == '\n') {
            break;
        }
        line.push_back(ch);
    }
    return line;
}

bool NetworkClient::IsConnected() const {
    return connected_;
}

void NetworkClient::Disconnect() {
    connected_ = false;
    CloseSocket();
    if (winsock_started_) {
        WSACleanup();
        winsock_started_ = false;
    }
}

void NetworkClient::CloseSocket() {
    if (socket_ != INVALID_SOCKET) {
        closesocket(socket_);
        socket_ = INVALID_SOCKET;
    }
}

std::string NetworkClient::BuildHelloJson(
    const std::string& room,
    const std::string& sender,
    const std::string& character_name,
    bool host_authority,
    const std::string& token
) const {
    std::ostringstream json;
    json << "{"
         << "\"type\":\"hello\","
         << "\"room\":\"" << room << "\","
         << "\"sender\":\"" << sender << "\","
         << "\"timestamp\":" << NowMs() << ","
         << "\"payload\":{"
         << "\"build\":\"pseudo-onblivion-dev\","
         << "\"protocolVersion\":1,"
         << "\"characterName\":\"" << character_name << "\","
         << "\"role\":\"" << (host_authority ? "host" : "peer") << "\","
         << "\"token\":\"" << token << "\""
         << "}}";
    return json.str();
}

}  // namespace pseudo_onblivion

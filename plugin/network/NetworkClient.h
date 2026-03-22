#pragma once

#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>

#include <atomic>
#include <mutex>
#include <string>

#pragma comment(lib, "Ws2_32.lib")

namespace pseudo_onblivion {

class NetworkClient {
  public:
    NetworkClient();
    ~NetworkClient();

    NetworkClient(const NetworkClient&) = delete;
    NetworkClient& operator=(const NetworkClient&) = delete;
    NetworkClient(NetworkClient&& other) noexcept;
    NetworkClient& operator=(NetworkClient&& other) noexcept;

    bool Connect(
        const std::string& host,
        unsigned short port,
        const std::string& room,
        const std::string& sender,
        const std::string& character_name,
        bool host_authority,
        const std::string& token
    );
    bool SendJson(const std::string& json);
    std::string ReceiveLine();
    bool IsConnected() const;
    void Disconnect();

  private:
    bool StartWinsock();
    void CloseSocket();
    std::string BuildHelloJson(
        const std::string& room,
        const std::string& sender,
        const std::string& character_name,
        bool host_authority,
        const std::string& token
    ) const;

    SOCKET socket_;
    std::atomic<bool> connected_;
    std::mutex send_mutex_;
    std::mutex receive_mutex_;
    bool winsock_started_;
};

}  // namespace pseudo_onblivion

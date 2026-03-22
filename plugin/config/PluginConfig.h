#pragma once

#include <string>

namespace pseudo_onblivion {

struct PluginConfig {
    std::string server_host = "127.0.0.1";
    unsigned short server_port = 7777;
    std::string room = "session-1";
    std::string player_id = "player-local";
    std::string character_name = "HeroOfKvatch";
    bool host_authority = false;
    std::string server_token;
    int send_interval_ms = 100;
    std::string log_path = "PseudoOnBlivion.log";
};

PluginConfig LoadPluginConfig(const std::string& path);

}  // namespace pseudo_onblivion

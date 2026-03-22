#include "PluginConfig.h"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <string>

namespace pseudo_onblivion {

namespace {

std::string Trim(std::string value) {
    auto not_space = [](unsigned char ch) { return !std::isspace(ch); };
    value.erase(value.begin(), std::find_if(value.begin(), value.end(), not_space));
    value.erase(std::find_if(value.rbegin(), value.rend(), not_space).base(), value.end());
    return value;
}

}  // namespace

PluginConfig LoadPluginConfig(const std::string& path) {
    PluginConfig config{};
    std::ifstream input(path);
    if (!input) {
        return config;
    }

    std::string line;
    while (std::getline(input, line)) {
        line = Trim(line);
        if (line.empty() || line[0] == ';' || line[0] == '#'
            || (line.front() == '[' && line.back() == ']')) {
            continue;
        }

        const std::size_t equals = line.find('=');
        if (equals == std::string::npos) {
            continue;
        }

        const std::string key = Trim(line.substr(0, equals));
        const std::string value = Trim(line.substr(equals + 1));

        if (key == "server_host") {
            config.server_host = value;
        } else if (key == "server_port") {
            config.server_port = static_cast<unsigned short>(std::stoi(value));
        } else if (key == "room") {
            config.room = value;
        } else if (key == "player_id") {
            config.player_id = value;
        } else if (key == "character_name") {
            config.character_name = value;
        } else if (key == "host_authority") {
            config.host_authority = (value == "1" || value == "true" || value == "TRUE" || value == "yes");
        } else if (key == "server_token") {
            config.server_token = value;
        } else if (key == "send_interval_ms") {
            config.send_interval_ms = std::stoi(value);
        } else if (key == "log_path") {
            config.log_path = value;
        }
    }

    return config;
}

}  // namespace pseudo_onblivion

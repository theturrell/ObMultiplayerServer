#pragma once

#include "SharedTypes.h"
#include "config/PluginConfig.h"
#include "game/GameAdapter.h"
#include "logging/Logger.h"
#include "network/NetworkClient.h"

#include <atomic>
#include <cstdint>
#include <deque>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

namespace pseudo_onblivion {

class PseudoOnBlivionPlugin {
  public:
    explicit PseudoOnBlivionPlugin(
        NetworkClient client,
        PluginConfig config,
        std::unique_ptr<GameAdapter> game_adapter,
        std::shared_ptr<Logger> logger
    );
    ~PseudoOnBlivionPlugin();

    bool Initialize();
    void Tick();
    void Start();
    void Stop();
    void PumpGameThreadWork();
    void ResetSessionState();
    void OnProtocolMismatch(std::int32_t protocol_version);

  private:
    bool TryParseRemotePlayerState(const std::string& message, RemotePlayerState& outState) const;
    bool TryParseRemoteAnimationEvent(const std::string& message, RemoteAnimationEvent& outEvent) const;
    bool TryParseRemoteCombatEvent(const std::string& message, RemoteCombatEvent& outEvent) const;
    bool TryParseRemoteQuestState(const std::string& message, RemoteQuestState& outState) const;
    bool TryParseRemoteLootState(const std::string& message, RemoteLootState& outState) const;
    bool TryParseWelcome(const std::string& message, std::int32_t& protocol_version) const;
    bool TryExtractString(const std::string& source, const std::string& key, std::string& value) const;
    bool TryExtractFloat(const std::string& source, const std::string& key, float& value) const;
    bool TryExtractInt32(const std::string& source, const std::string& key, std::int32_t& value) const;
    bool TryExtractInt64(const std::string& source, const std::string& key, std::int64_t& value) const;
    bool TryExtractBool(const std::string& source, const std::string& key, bool& value) const;
    bool TryExtractCharacterProfile(const std::string& source, CharacterProfile& profile) const;
    bool TryParsePeerLeft(const std::string& message, std::string& sender) const;
    void RunSendLoop();
    void HandleIncomingMessage(const std::string& message);

    NetworkClient client_;
    PluginConfig config_;
    std::unique_ptr<GameAdapter> game_adapter_;
    std::shared_ptr<Logger> logger_;
    std::atomic<bool> running_;
    std::mutex inbound_mutex_;
    std::deque<RemotePlayerState> inbound_player_states_;
    std::deque<RemoteAnimationEvent> inbound_animation_events_;
    std::deque<RemoteCombatEvent> inbound_combat_events_;
    std::deque<RemoteQuestState> inbound_quest_states_;
    std::deque<RemoteLootState> inbound_loot_states_;
    std::deque<std::string> departed_peers_;
    std::map<std::string, RemotePlayerState> remote_players_;
    PlayerSnapshot last_snapshot_{};
    bool has_last_snapshot_;
    bool last_combat_state_;
    std::string last_animation_group_;
    std::atomic<bool> protocol_mismatch_;
    std::thread send_thread_;
    std::thread receive_thread_;
};

}  // namespace pseudo_onblivion

#include "PseudoOnBlivionPlugin.h"

#include <chrono>
#include <cstdlib>
#include <sstream>
#include <thread>

namespace pseudo_onblivion {

namespace {
constexpr std::int32_t kProtocolVersion = 1;

std::int64_t NowMs() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count();
}

std::string JsonEscape(const std::string& value) {
    std::string escaped;
    escaped.reserve(value.size());
    for (const char ch : value) {
        switch (ch) {
        case '\\':
            escaped += "\\\\";
            break;
        case '"':
            escaped += "\\\"";
            break;
        case '\n':
            escaped += "\\n";
            break;
        case '\r':
            escaped += "\\r";
            break;
        case '\t':
            escaped += "\\t";
            break;
        default:
            escaped.push_back(ch);
            break;
        }
    }
    return escaped;
}

std::string BuildCharacterProfileJson(const CharacterProfile& profile) {
    std::ostringstream json;
    json << "\"profile\":{"
         << "\"characterName\":\"" << JsonEscape(profile.characterName) << "\","
         << "\"raceFormId\":\"" << JsonEscape(profile.raceFormId) << "\","
         << "\"raceName\":\"" << JsonEscape(profile.raceName) << "\","
         << "\"classFormId\":\"" << JsonEscape(profile.classFormId) << "\","
         << "\"className\":\"" << JsonEscape(profile.className) << "\","
         << "\"birthsignFormId\":\"" << JsonEscape(profile.birthsignFormId) << "\","
         << "\"birthsignName\":\"" << JsonEscape(profile.birthsignName) << "\","
         << "\"hairFormId\":\"" << JsonEscape(profile.hairFormId) << "\","
         << "\"hairName\":\"" << JsonEscape(profile.hairName) << "\","
         << "\"eyesFormId\":\"" << JsonEscape(profile.eyesFormId) << "\","
         << "\"eyesName\":\"" << JsonEscape(profile.eyesName) << "\","
         << "\"isFemale\":" << (profile.isFemale ? "true" : "false") << ","
         << "\"scale\":" << profile.scale << ","
         << "\"hairColorR\":" << profile.hairColorR << ","
         << "\"hairColorG\":" << profile.hairColorG << ","
         << "\"hairColorB\":" << profile.hairColorB
         << "}";
    return json.str();
}

std::string BuildPlayerStateJson(
    const PluginConfig& config,
    const PlayerSnapshot& snapshot
) {
    std::ostringstream json;
    json << "{"
         << "\"type\":\"player_state\","
         << "\"room\":\"" << JsonEscape(config.room) << "\","
         << "\"sender\":\"" << JsonEscape(config.player_id) << "\","
         << "\"timestamp\":" << NowMs() << ","
         << "\"payload\":{"
         << "\"position\":{\"x\":" << snapshot.position.x
         << ",\"y\":" << snapshot.position.y
         << ",\"z\":" << snapshot.position.z << "},"
         << "\"rotation\":{\"x\":" << snapshot.rotation.x
         << ",\"y\":" << snapshot.rotation.y
         << ",\"z\":" << snapshot.rotation.z << "},"
         << "\"cell\":\"" << JsonEscape(snapshot.cell) << "\","
         << "\"isInCombat\":" << (snapshot.isInCombat ? "true" : "false") << ","
         << "\"health\":" << snapshot.health << ","
         << "\"magicka\":" << snapshot.magicka << ","
         << "\"stamina\":" << snapshot.stamina << ","
         << "\"equippedWeaponFormId\":\"" << JsonEscape(snapshot.equippedWeaponFormId) << "\","
         << "\"combatTargetRefId\":\"" << JsonEscape(snapshot.combatTargetRefId) << "\","
         << BuildCharacterProfileJson(snapshot.profile)
         << "}}";
    return json.str();
}

std::string BuildAnimationEventJson(
    const PluginConfig& config,
    const std::string& group,
    bool loop
) {
    std::ostringstream json;
    json << "{"
         << "\"type\":\"animation_event\","
         << "\"room\":\"" << JsonEscape(config.room) << "\","
         << "\"sender\":\"" << JsonEscape(config.player_id) << "\","
         << "\"timestamp\":" << NowMs() << ","
         << "\"payload\":{"
         << "\"group\":\"" << JsonEscape(group) << "\","
         << "\"loop\":" << (loop ? "true" : "false")
         << "}}";
    return json.str();
}

std::string BuildCombatEventJson(
    const PluginConfig& config,
    const std::string& kind,
    const std::string& target_ref_id
) {
    std::ostringstream json;
    json << "{"
         << "\"type\":\"combat_event\","
         << "\"room\":\"" << JsonEscape(config.room) << "\","
         << "\"sender\":\"" << JsonEscape(config.player_id) << "\","
         << "\"timestamp\":" << NowMs() << ","
         << "\"payload\":{"
         << "\"kind\":\"" << JsonEscape(kind) << "\","
         << "\"targetRefId\":\"" << JsonEscape(target_ref_id) << "\","
         << "\"weaponFormId\":\"\"," 
         << "\"damage\":0"
         << "}}";
    return json.str();
}

std::string DeriveAnimationGroup(
    const PlayerSnapshot& current,
    const PlayerSnapshot& previous
) {
    const float dx = current.position.x - previous.position.x;
    const float dy = current.position.y - previous.position.y;
    const float dz = current.position.z - previous.position.z;
    const float distance_sq = (dx * dx) + (dy * dy) + (dz * dz);

    if (distance_sq < 9.0f) {
        return current.isInCombat ? "IdleCombat" : "Idle";
    }

    return current.isInCombat ? "AttackLeft" : "Forward";
}

}  // namespace

PseudoOnBlivionPlugin::PseudoOnBlivionPlugin(
    NetworkClient client,
    PluginConfig config,
    std::unique_ptr<GameAdapter> game_adapter,
    std::shared_ptr<Logger> logger
)
    : client_(std::move(client)),
      config_(std::move(config)),
      game_adapter_(std::move(game_adapter)),
      logger_(std::move(logger)),
      has_last_snapshot_(false),
      last_combat_state_(false),
      running_(false),
      protocol_mismatch_(false) {}

PseudoOnBlivionPlugin::~PseudoOnBlivionPlugin() {
    Stop();
}

bool PseudoOnBlivionPlugin::Initialize() {
    logger_->Info("Initializing Pseudo-OnBlivion plugin transport");
    const bool connected = client_.Connect(
        config_.server_host,
        config_.server_port,
        config_.room,
        config_.player_id,
        config_.character_name,
        config_.host_authority,
        config_.server_token
    );
    if (!connected) {
        logger_->Error("Failed to connect to relay server");
        return false;
    }

    logger_->Info("Connected to relay server");
    return true;
}

void PseudoOnBlivionPlugin::Tick() {
    if (!client_.IsConnected() || protocol_mismatch_) {
        return;
    }

    PlayerSnapshot snapshot{};
    if (!game_adapter_ || !game_adapter_->CaptureLocalPlayerSnapshot(snapshot)) {
        logger_->Debug("Local player snapshot capture unavailable for this tick");
        return;
    }

    client_.SendJson(BuildPlayerStateJson(config_, snapshot));

    if (has_last_snapshot_) {
        const std::string animation_group = DeriveAnimationGroup(snapshot, last_snapshot_);
        if (animation_group != last_animation_group_) {
            client_.SendJson(BuildAnimationEventJson(config_, animation_group, true));
            last_animation_group_ = animation_group;
        }
    } else {
        last_animation_group_ = snapshot.isInCombat ? "IdleCombat" : "Idle";
        client_.SendJson(BuildAnimationEventJson(config_, last_animation_group_, true));
    }

    if (!has_last_snapshot_ || snapshot.isInCombat != last_combat_state_) {
        client_.SendJson(
            BuildCombatEventJson(
                config_,
                snapshot.isInCombat ? "enter_combat" : "leave_combat",
                snapshot.combatTargetRefId
            )
        );
        last_combat_state_ = snapshot.isInCombat;
    }

    last_snapshot_ = snapshot;
    has_last_snapshot_ = true;
}

void PseudoOnBlivionPlugin::Start() {
    if (running_) {
        return;
    }

    running_ = true;
    receive_thread_ = std::thread([this]() {
        while (running_ && client_.IsConnected()) {
            const std::string message = client_.ReceiveLine();
            if (message.empty()) {
                continue;
            }
            HandleIncomingMessage(message);
        }
    });
}

void PseudoOnBlivionPlugin::Stop() {
    if (!running_) {
        client_.Disconnect();
        return;
    }

    running_ = false;
    client_.Disconnect();

    if (send_thread_.joinable()) {
        send_thread_.join();
    }
    if (receive_thread_.joinable()) {
        receive_thread_.join();
    }
}

void PseudoOnBlivionPlugin::RunSendLoop() {
    while (running_ && client_.IsConnected()) {
        Tick();
        std::this_thread::sleep_for(std::chrono::milliseconds(config_.send_interval_ms));
    }
}

void PseudoOnBlivionPlugin::HandleIncomingMessage(const std::string& message) {
    std::int32_t protocol_version = 0;
    if (TryParseWelcome(message, protocol_version) && protocol_version != kProtocolVersion) {
        OnProtocolMismatch(protocol_version);
        return;
    }

    RemotePlayerState state{};
    if (TryParseRemotePlayerState(message, state)) {
        std::lock_guard<std::mutex> lock(inbound_mutex_);
        inbound_player_states_.push_back(state);
        if (inbound_player_states_.size() > 128) {
            inbound_player_states_.pop_front();
        }
        return;
    }

    RemoteQuestState quest_state{};
    if (TryParseRemoteQuestState(message, quest_state)) {
        std::lock_guard<std::mutex> lock(inbound_mutex_);
        inbound_quest_states_.push_back(quest_state);
        if (inbound_quest_states_.size() > 128) {
            inbound_quest_states_.pop_front();
        }
        return;
    }

    RemoteAnimationEvent animation_event{};
    if (TryParseRemoteAnimationEvent(message, animation_event)) {
        std::lock_guard<std::mutex> lock(inbound_mutex_);
        inbound_animation_events_.push_back(animation_event);
        if (inbound_animation_events_.size() > 128) {
            inbound_animation_events_.pop_front();
        }
        return;
    }

    RemoteCombatEvent combat_event{};
    if (TryParseRemoteCombatEvent(message, combat_event)) {
        std::lock_guard<std::mutex> lock(inbound_mutex_);
        inbound_combat_events_.push_back(combat_event);
        if (inbound_combat_events_.size() > 128) {
            inbound_combat_events_.pop_front();
        }
        return;
    }

    RemoteLootState loot_state{};
    if (TryParseRemoteLootState(message, loot_state)) {
        std::lock_guard<std::mutex> lock(inbound_mutex_);
        inbound_loot_states_.push_back(loot_state);
        if (inbound_loot_states_.size() > 128) {
            inbound_loot_states_.pop_front();
        }
        return;
    }

    std::string departed_sender;
    if (TryParsePeerLeft(message, departed_sender)) {
        std::lock_guard<std::mutex> lock(inbound_mutex_);
        departed_peers_.push_back(departed_sender);
        return;
    }

    logger_->Debug(std::string("Received non-player-state relay message: ") + message);
}

void PseudoOnBlivionPlugin::PumpGameThreadWork() {
    Tick();

    std::deque<RemotePlayerState> pending;
    std::deque<RemoteAnimationEvent> pending_animation;
    std::deque<RemoteCombatEvent> pending_combat;
    std::deque<RemoteQuestState> pending_quests;
    std::deque<RemoteLootState> pending_loot;
    std::deque<std::string> departed;
    {
        std::lock_guard<std::mutex> lock(inbound_mutex_);
        pending.swap(inbound_player_states_);
        pending_animation.swap(inbound_animation_events_);
        pending_combat.swap(inbound_combat_events_);
        pending_quests.swap(inbound_quest_states_);
        pending_loot.swap(inbound_loot_states_);
        departed.swap(departed_peers_);
    }

    while (!departed.empty()) {
        const std::string sender = departed.front();
        departed.pop_front();
        remote_players_.erase(sender);
        if (game_adapter_) {
            game_adapter_->RemoveRemotePlayer(sender);
        }
    }

    while (!pending.empty()) {
        const RemotePlayerState state = pending.front();
        pending.pop_front();
        remote_players_[state.sender] = state;

        if (game_adapter_) {
            game_adapter_->ApplyRemotePlayerState(state);
        }

        logger_->Debug(
            std::string("Queued remote player update applied for ")
            + state.sender + " in cell " + state.cell
        );
    }

    while (!pending_animation.empty()) {
        const RemoteAnimationEvent event = pending_animation.front();
        pending_animation.pop_front();
        if (game_adapter_) {
            game_adapter_->ApplyRemoteAnimationEvent(event);
        }
    }

    while (!pending_combat.empty()) {
        const RemoteCombatEvent event = pending_combat.front();
        pending_combat.pop_front();
        if (game_adapter_) {
            game_adapter_->ApplyRemoteCombatEvent(event);
        }
    }

    while (!pending_quests.empty()) {
        const RemoteQuestState state = pending_quests.front();
        pending_quests.pop_front();
        if (game_adapter_) {
            game_adapter_->ApplyRemoteQuestState(state);
        }
    }

    while (!pending_loot.empty()) {
        const RemoteLootState state = pending_loot.front();
        pending_loot.pop_front();
        if (game_adapter_) {
            game_adapter_->ApplyRemoteLootState(state);
        }
    }

    if (game_adapter_) {
        game_adapter_->Update();
    }
}

void PseudoOnBlivionPlugin::ResetSessionState() {
    {
        std::lock_guard<std::mutex> lock(inbound_mutex_);
        inbound_player_states_.clear();
        inbound_animation_events_.clear();
        inbound_combat_events_.clear();
        inbound_quest_states_.clear();
        inbound_loot_states_.clear();
        departed_peers_.clear();
    }

    remote_players_.clear();
    has_last_snapshot_ = false;
    last_combat_state_ = false;
    last_animation_group_.clear();
    protocol_mismatch_ = false;

    if (game_adapter_) {
        game_adapter_->ResetWorldState();
    }
}

void PseudoOnBlivionPlugin::OnProtocolMismatch(std::int32_t protocol_version) {
    protocol_mismatch_ = true;
    if (logger_) {
        logger_->Error(
            "Relay protocol mismatch. Client expects " + std::to_string(kProtocolVersion)
            + " but server reported " + std::to_string(protocol_version)
        );
    }
    client_.Disconnect();
}

bool PseudoOnBlivionPlugin::TryParseRemotePlayerState(
    const std::string& message,
    RemotePlayerState& outState
) const {
    std::string type;
    if (!TryExtractString(message, "\"type\"", type) || type != "player_state") {
        return false;
    }

    std::string sender;
    std::string cell;
    float px = 0.0f;
    float py = 0.0f;
    float pz = 0.0f;
    float rx = 0.0f;
    float ry = 0.0f;
    float rz = 0.0f;
    float health = 0.0f;
    float magicka = 0.0f;
    float stamina = 0.0f;
    bool is_in_combat = false;
    std::int64_t timestamp = 0;

    if (!TryExtractString(message, "\"sender\"", sender)
        || !TryExtractString(message, "\"cell\"", cell)
        || !TryExtractFloat(message, "\"x\"", px)
        || !TryExtractFloat(message, "\"y\"", py)
        || !TryExtractFloat(message, "\"z\"", pz)
        || !TryExtractFloat(message, "\"health\"", health)
        || !TryExtractFloat(message, "\"magicka\"", magicka)
        || !TryExtractFloat(message, "\"stamina\"", stamina)
        || !TryExtractBool(message, "\"isInCombat\"", is_in_combat)
        || !TryExtractInt64(message, "\"timestamp\"", timestamp)) {
        return false;
    }

    const std::size_t rotation_pos = message.find("\"rotation\"");
    if (rotation_pos != std::string::npos) {
        const std::string rotation_slice = message.substr(rotation_pos);
        TryExtractFloat(rotation_slice, "\"x\"", rx);
        TryExtractFloat(rotation_slice, "\"y\"", ry);
        TryExtractFloat(rotation_slice, "\"z\"", rz);
    }

    outState.sender = sender;
    outState.cell = cell;
    outState.position = {px, py, pz};
    outState.rotation = {rx, ry, rz};
    outState.health = health;
    outState.magicka = magicka;
    outState.stamina = stamina;
    TryExtractString(message, "\"equippedWeaponFormId\"", outState.equippedWeaponFormId);
    TryExtractString(message, "\"combatTargetRefId\"", outState.combatTargetRefId);
    outState.isInCombat = is_in_combat;
    outState.timestamp = timestamp;
    TryExtractCharacterProfile(message, outState.profile);
    return true;
}

bool PseudoOnBlivionPlugin::TryParseRemoteQuestState(
    const std::string& message,
    RemoteQuestState& outState
) const {
    std::string type;
    if (!TryExtractString(message, "\"type\"", type) || type != "quest_state") {
        return false;
    }

    std::string sender;
    std::string quest_id;
    std::string status;
    std::int32_t stage = 0;
    std::int64_t timestamp = 0;

    if (!TryExtractString(message, "\"sender\"", sender)
        || !TryExtractString(message, "\"questId\"", quest_id)
        || !TryExtractString(message, "\"status\"", status)
        || !TryExtractInt32(message, "\"stage\"", stage)
        || !TryExtractInt64(message, "\"timestamp\"", timestamp)) {
        return false;
    }

    outState.sender = sender;
    outState.questId = quest_id;
    outState.status = status;
    outState.stage = stage;
    outState.objectiveIndex = -1;
    outState.objectiveCompleted = false;
    outState.objectiveDisplayed = false;
    outState.completed = false;
    outState.failed = false;
    outState.makeActive = false;
    TryExtractInt32(message, "\"objectiveIndex\"", outState.objectiveIndex);
    TryExtractBool(message, "\"objectiveCompleted\"", outState.objectiveCompleted);
    TryExtractBool(message, "\"objectiveDisplayed\"", outState.objectiveDisplayed);
    TryExtractBool(message, "\"completed\"", outState.completed);
    TryExtractBool(message, "\"failed\"", outState.failed);
    TryExtractBool(message, "\"makeActive\"", outState.makeActive);
    TryExtractString(message, "\"scriptLine\"", outState.scriptLine);
    outState.timestamp = timestamp;
    return true;
}

bool PseudoOnBlivionPlugin::TryParseRemoteAnimationEvent(
    const std::string& message,
    RemoteAnimationEvent& outEvent
) const {
    std::string type;
    if (!TryExtractString(message, "\"type\"", type) || type != "animation_event") {
        return false;
    }

    if (!TryExtractString(message, "\"sender\"", outEvent.sender)
        || !TryExtractString(message, "\"group\"", outEvent.group)
        || !TryExtractBool(message, "\"loop\"", outEvent.loop)
        || !TryExtractInt64(message, "\"timestamp\"", outEvent.timestamp)) {
        return false;
    }

    return true;
}

bool PseudoOnBlivionPlugin::TryParseRemoteCombatEvent(
    const std::string& message,
    RemoteCombatEvent& outEvent
) const {
    std::string type;
    if (!TryExtractString(message, "\"type\"", type) || type != "combat_event") {
        return false;
    }

    if (!TryExtractString(message, "\"sender\"", outEvent.sender)
        || !TryExtractString(message, "\"kind\"", outEvent.kind)
        || !TryExtractInt64(message, "\"timestamp\"", outEvent.timestamp)) {
        return false;
    }

    outEvent.targetRefId.clear();
    outEvent.weaponFormId.clear();
    outEvent.damage = 0.0f;
    TryExtractString(message, "\"targetRefId\"", outEvent.targetRefId);
    TryExtractString(message, "\"weaponFormId\"", outEvent.weaponFormId);
    TryExtractFloat(message, "\"damage\"", outEvent.damage);
    return true;
}

bool PseudoOnBlivionPlugin::TryParseRemoteLootState(
    const std::string& message,
    RemoteLootState& outState
) const {
    std::string type;
    if (!TryExtractString(message, "\"type\"", type) || type != "loot_state") {
        return false;
    }

    std::string sender;
    std::string loot_id;
    std::string action;
    std::string form_id;
    std::int32_t count = 0;
    bool removed = false;
    std::int64_t timestamp = 0;

    if (!TryExtractString(message, "\"sender\"", sender)
        || !TryExtractString(message, "\"lootId\"", loot_id)
        || !TryExtractString(message, "\"action\"", action)
        || !TryExtractString(message, "\"formId\"", form_id)
        || !TryExtractInt32(message, "\"count\"", count)
        || !TryExtractBool(message, "\"removed\"", removed)
        || !TryExtractInt64(message, "\"timestamp\"", timestamp)) {
        return false;
    }

    outState.sender = sender;
    outState.lootId = loot_id;
    outState.action = action;
    outState.formId = form_id;
    TryExtractString(message, "\"containerRefId\"", outState.containerRefId);
    TryExtractString(message, "\"itemRefId\"", outState.itemRefId);
    TryExtractString(message, "\"cell\"", outState.cell);
    TryExtractBool(message, "\"isWorldObject\"", outState.isWorldObject);
    outState.count = count;
    outState.removed = removed;
    outState.timestamp = timestamp;

    const std::size_t position_pos = message.find("\"position\"");
    if (position_pos != std::string::npos) {
        const std::string position_slice = message.substr(position_pos);
        if (TryExtractFloat(position_slice, "\"x\"", outState.position.x)
            && TryExtractFloat(position_slice, "\"y\"", outState.position.y)
            && TryExtractFloat(position_slice, "\"z\"", outState.position.z)) {
            outState.hasTransform = true;
        }
    }

    const std::size_t rotation_pos = message.find("\"rotation\"");
    if (rotation_pos != std::string::npos) {
        const std::string rotation_slice = message.substr(rotation_pos);
        TryExtractFloat(rotation_slice, "\"x\"", outState.rotation.x);
        TryExtractFloat(rotation_slice, "\"y\"", outState.rotation.y);
        TryExtractFloat(rotation_slice, "\"z\"", outState.rotation.z);
    }

    return true;
}

bool PseudoOnBlivionPlugin::TryParseWelcome(
    const std::string& message,
    std::int32_t& protocol_version
) const {
    std::string type;
    if (!TryExtractString(message, "\"type\"", type) || type != "welcome") {
        return false;
    }

    return TryExtractInt32(message, "\"protocolVersion\"", protocol_version);
}

bool PseudoOnBlivionPlugin::TryParsePeerLeft(
    const std::string& message,
    std::string& sender
) const {
    std::string type;
    if (!TryExtractString(message, "\"type\"", type) || type != "peer_left") {
        return false;
    }

    if (!TryExtractString(message, "\"sessionId\"", sender)) {
        return false;
    }

    return true;
}

bool PseudoOnBlivionPlugin::TryExtractString(
    const std::string& source,
    const std::string& key,
    std::string& value
) const {
    const std::size_t key_pos = source.find(key);
    if (key_pos == std::string::npos) {
        return false;
    }

    const std::size_t colon = source.find(':', key_pos + key.size());
    const std::size_t first_quote = source.find('"', colon + 1);
    const std::size_t second_quote = source.find('"', first_quote + 1);
    if (colon == std::string::npos || first_quote == std::string::npos || second_quote == std::string::npos) {
        return false;
    }

    value = source.substr(first_quote + 1, second_quote - first_quote - 1);
    return true;
}

bool PseudoOnBlivionPlugin::TryExtractFloat(
    const std::string& source,
    const std::string& key,
    float& value
) const {
    const std::size_t key_pos = source.find(key);
    if (key_pos == std::string::npos) {
        return false;
    }

    const std::size_t colon = source.find(':', key_pos + key.size());
    if (colon == std::string::npos) {
        return false;
    }

    char* end_ptr = nullptr;
    value = std::strtof(source.c_str() + colon + 1, &end_ptr);
    return end_ptr != source.c_str() + colon + 1;
}

bool PseudoOnBlivionPlugin::TryExtractInt32(
    const std::string& source,
    const std::string& key,
    std::int32_t& value
) const {
    const std::size_t key_pos = source.find(key);
    if (key_pos == std::string::npos) {
        return false;
    }

    const std::size_t colon = source.find(':', key_pos + key.size());
    if (colon == std::string::npos) {
        return false;
    }

    char* end_ptr = nullptr;
    value = static_cast<std::int32_t>(std::strtol(source.c_str() + colon + 1, &end_ptr, 10));
    return end_ptr != source.c_str() + colon + 1;
}

bool PseudoOnBlivionPlugin::TryExtractInt64(
    const std::string& source,
    const std::string& key,
    std::int64_t& value
) const {
    const std::size_t key_pos = source.find(key);
    if (key_pos == std::string::npos) {
        return false;
    }

    const std::size_t colon = source.find(':', key_pos + key.size());
    if (colon == std::string::npos) {
        return false;
    }

    char* end_ptr = nullptr;
    value = std::strtoll(source.c_str() + colon + 1, &end_ptr, 10);
    return end_ptr != source.c_str() + colon + 1;
}

bool PseudoOnBlivionPlugin::TryExtractBool(
    const std::string& source,
    const std::string& key,
    bool& value
) const {
    const std::size_t key_pos = source.find(key);
    if (key_pos == std::string::npos) {
        return false;
    }

    const std::size_t colon = source.find(':', key_pos + key.size());
    if (colon == std::string::npos) {
        return false;
    }

    const std::size_t value_start = source.find_first_not_of(" \t\r\n", colon + 1);
    if (value_start == std::string::npos) {
        return false;
    }

    if (source.compare(value_start, 4, "true") == 0) {
        value = true;
        return true;
    }
    if (source.compare(value_start, 5, "false") == 0) {
        value = false;
        return true;
    }
    return false;
}

bool PseudoOnBlivionPlugin::TryExtractCharacterProfile(
    const std::string& source,
    CharacterProfile& profile
) const {
    TryExtractString(source, "\"characterName\"", profile.characterName);
    TryExtractString(source, "\"raceFormId\"", profile.raceFormId);
    TryExtractString(source, "\"raceName\"", profile.raceName);
    TryExtractString(source, "\"classFormId\"", profile.classFormId);
    TryExtractString(source, "\"className\"", profile.className);
    TryExtractString(source, "\"birthsignFormId\"", profile.birthsignFormId);
    TryExtractString(source, "\"birthsignName\"", profile.birthsignName);
    TryExtractString(source, "\"hairFormId\"", profile.hairFormId);
    TryExtractString(source, "\"hairName\"", profile.hairName);
    TryExtractString(source, "\"eyesFormId\"", profile.eyesFormId);
    TryExtractString(source, "\"eyesName\"", profile.eyesName);
    TryExtractBool(source, "\"isFemale\"", profile.isFemale);
    TryExtractFloat(source, "\"scale\"", profile.scale);
    TryExtractInt32(source, "\"hairColorR\"", profile.hairColorR);
    TryExtractInt32(source, "\"hairColorG\"", profile.hairColorG);
    TryExtractInt32(source, "\"hairColorB\"", profile.hairColorB);
    return true;
}

}  // namespace pseudo_onblivion

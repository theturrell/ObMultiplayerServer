#include "GameAdapter.h"

#include "IPrefix.h"
#include "obse/PluginAPI.h"
#include "obse/GameActorValues.h"
#include "obse/GameTypes.h"
#include "obse/GameAPI.h"
#include "obse/GameForms.h"
#include "obse/GameObjects.h"

#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <iomanip>
#include <map>
#include <set>
#include <memory>
#include <sstream>

namespace pseudo_onblivion {

namespace {

constexpr std::uintptr_t kPlayerPointerAddress = 0x00B333C4;
constexpr std::uintptr_t kLookupFormByIdAddress = 0x0046B250;
constexpr std::uint8_t kCellFlagInterior = 1 << 0;
constexpr float kRadiansToDegrees = 57.2957795131f;
constexpr float kProxySmoothingFactor = 0.35f;
constexpr float kSnapDistance = 384.0f;
constexpr std::int64_t kProxyStaleAfterMs = 8000;
constexpr float kHealthDesyncTolerance = 1.0f;
constexpr float kMagickaDesyncTolerance = 1.0f;
constexpr float kStaminaDesyncTolerance = 1.0f;

struct RuntimeString {
    char* data;
    std::uint16_t length;
    std::uint16_t capacity;
};

struct RuntimeFullName {
    void* vtable;
    RuntimeString name;
};

struct RuntimeCellCoordinates {
    std::int32_t x;
    std::int32_t y;
};

struct RuntimeWorldSpace {
    std::array<std::byte, 0x18> pad0{};
    RuntimeFullName full_name{};
};

struct RuntimeCell {
    std::array<std::byte, 0x18> pad0{};
    RuntimeFullName full_name{};
    std::uint8_t flags0 = 0;
    std::uint8_t flags1 = 0;
    std::uint8_t cell_process_level = 0;
    std::uint8_t pad27 = 0;
    std::array<std::byte, 0x14> pad28{};
    RuntimeCellCoordinates* coordinates = nullptr;
    std::array<std::byte, 0x10> pad40{};
    RuntimeWorldSpace* world_space = nullptr;
};

struct RuntimePlayerCharacter {
    std::array<std::byte, 0x20> pad0{};
    float rot_x = 0.0f;
    float rot_y = 0.0f;
    float rot_z = 0.0f;
    float pos_x = 0.0f;
    float pos_y = 0.0f;
    float pos_z = 0.0f;
    float scale = 1.0f;
    void* ni_node = nullptr;
    RuntimeCell* parent_cell = nullptr;
    std::array<std::byte, 0x400> pad44{};
    float health = 0.0f;
    float magicka = 0.0f;
    float stamina = 0.0f;
};

static_assert(offsetof(RuntimeCell, full_name) == 0x18);
static_assert(offsetof(RuntimeCell, flags0) == 0x24);
static_assert(offsetof(RuntimeCell, coordinates) == 0x3C);
static_assert(offsetof(RuntimeCell, world_space) == 0x50);
static_assert(offsetof(RuntimeWorldSpace, full_name) == 0x18);
static_assert(offsetof(RuntimePlayerCharacter, rot_x) == 0x20);
static_assert(offsetof(RuntimePlayerCharacter, pos_x) == 0x2C);
static_assert(offsetof(RuntimePlayerCharacter, parent_cell) == 0x40);
static_assert(offsetof(RuntimePlayerCharacter, health) == 0x444);

RuntimePlayerCharacter* GetPlayerCharacter() {
    auto*** player_handle = reinterpret_cast<RuntimePlayerCharacter***>(kPlayerPointerAddress);
    if (player_handle == nullptr || *player_handle == nullptr) {
        return nullptr;
    }

    return **player_handle;
}

std::string SafeName(const RuntimeString& value) {
    if (value.data != nullptr && value.length > 0) {
        return std::string(value.data, value.length);
    }
    return {};
}

std::string SafeBsString(const BSStringT& value) {
    return value.m_data != nullptr ? value.m_data : std::string();
}

std::string FormDisplayName(TESForm* form) {
    if (form == nullptr) {
        return {};
    }

    switch (form->typeID) {
    case kFormType_Class:
        return SafeBsString(reinterpret_cast<TESClass*>(form)->fullName.name);
    case kFormType_Race:
        return SafeBsString(reinterpret_cast<TESRace*>(form)->fullName.name);
    case kFormType_BirthSign:
        return SafeBsString(reinterpret_cast<BirthSign*>(form)->fullName.name);
    case kFormType_Hair:
        return SafeBsString(reinterpret_cast<TESHair*>(form)->fullName.name);
    case kFormType_Eyes:
        return SafeBsString(reinterpret_cast<TESEyes*>(form)->fullName.name);
    case kFormType_NPC:
        return SafeBsString(reinterpret_cast<TESNPC*>(form)->fullName.name);
    default:
        return {};
    }
}

std::string QuoteConsoleString(std::string value) {
    std::string escaped;
    escaped.reserve(value.size() + 2);
    escaped.push_back('"');
    for (const char ch : value) {
        if (ch == '"') {
            escaped.push_back('\'');
        } else {
            escaped.push_back(ch);
        }
    }
    escaped.push_back('"');
    return escaped;
}

std::string DescribeCell(const RuntimeCell* cell) {
    if (cell == nullptr) {
        return "UNRESOLVED_RUNTIME";
    }

    const std::string cell_name = SafeName(cell->full_name.name);
    if (!cell_name.empty()) {
        return cell_name;
    }

    if ((cell->flags0 & kCellFlagInterior) == 0 && cell->world_space != nullptr) {
        const std::string world_name = SafeName(cell->world_space->full_name.name);
        std::ostringstream description;
        if (!world_name.empty()) {
            description << world_name;
        } else {
            description << "EXTERIOR";
        }

        if (cell->coordinates != nullptr) {
            description << " [" << cell->coordinates->x << "," << cell->coordinates->y << "]";
        }
        return description.str();
    }

    return "INTERIOR_UNNAMED";
}

float Lerp(float from, float to, float alpha) {
    return from + ((to - from) * alpha);
}

float AxisDistance(float a, float b) {
    return (a > b) ? (a - b) : (b - a);
}

float ClampNonNegative(float value) {
    return value < 0.0f ? 0.0f : value;
}

using LookupFormByIdFn = TESForm* (__cdecl*)(UInt32 id);

std::uint32_t ParseFormId(const std::string& text) {
    if (text.empty()) {
        return 0;
    }

    char* end_ptr = nullptr;
    return static_cast<std::uint32_t>(std::strtoul(text.c_str(), &end_ptr, 0));
}

TESForm* LookupRuntimeFormById(UInt32 id) {
    if (id == 0) {
        return nullptr;
    }

    auto* const lookup = reinterpret_cast<LookupFormByIdFn>(kLookupFormByIdAddress);
    return lookup != nullptr ? lookup(id) : nullptr;
}

class RuntimeBackedGameAdapter : public GameAdapter {
  public:
    RuntimeBackedGameAdapter(
        std::shared_ptr<Logger> logger,
        OBSEConsoleInterface* console
    )
        : logger_(std::move(logger)),
          console_(console),
          announced_remote_peer_(false) {}

    bool CaptureLocalPlayerSnapshot(PlayerSnapshot& snapshot) override {
        RuntimePlayerCharacter* const player = GetPlayerCharacter();
        if (player == nullptr || player->parent_cell == nullptr) {
            if (logger_ && !warned_about_placeholder_) {
                warned_about_placeholder_ = true;
                logger_->Info(
                    "Game runtime not ready yet. Waiting for the player and parent cell "
                    "before emitting local state."
                );
            }
            return false;
        }

        snapshot.position = {player->pos_x, player->pos_y, player->pos_z};
        snapshot.rotation = {player->rot_x, player->rot_y, player->rot_z};
        snapshot.cell = DescribeCell(player->parent_cell);
        snapshot.health = player->health;
        snapshot.magicka = player->magicka;
        snapshot.stamina = player->stamina;
        auto* const actor = reinterpret_cast<PlayerCharacter*>(player);
        auto* const actor_base = reinterpret_cast<TESNPC*>(actor->baseForm);
        snapshot.equippedWeaponFormId.clear();
        snapshot.isInCombat = actor->IsInCombat(false);
        if (TESForm* const combat_target = actor->GetCombatTarget()) {
            snapshot.combatTargetRefId = FormatFormId(combat_target);
        } else {
            snapshot.combatTargetRefId.clear();
        }

        snapshot.profile = {};
        snapshot.profile.scale = player->scale;
        if (actor_base != nullptr) {
            snapshot.profile.characterName = FormDisplayName(actor_base);
            snapshot.profile.isFemale = actor_base->actorBaseData.IsFemale();
            snapshot.profile.hairColorR = actor_base->hairColorRGB[0];
            snapshot.profile.hairColorG = actor_base->hairColorRGB[1];
            snapshot.profile.hairColorB = actor_base->hairColorRGB[2];

            if (actor_base->race.race != nullptr) {
                snapshot.profile.raceFormId = FormatFormId(actor_base->race.race);
                snapshot.profile.raceName = FormDisplayName(actor_base->race.race);
            }

            if (TESClass* const player_class = actor_base->npcClass) {
                snapshot.profile.classFormId = FormatFormId(player_class);
                snapshot.profile.className = FormDisplayName(player_class);
            }

            if (actor_base->hair != nullptr) {
                snapshot.profile.hairFormId = FormatFormId(actor_base->hair);
                snapshot.profile.hairName = FormDisplayName(actor_base->hair);
            }

            if (actor_base->eyes != nullptr) {
                snapshot.profile.eyesFormId = FormatFormId(actor_base->eyes);
                snapshot.profile.eyesName = FormDisplayName(actor_base->eyes);
            }
        }

        if (actor->birthSign != nullptr) {
            snapshot.profile.birthsignFormId = FormatFormId(actor->birthSign);
            snapshot.profile.birthsignName = FormDisplayName(actor->birthSign);
        }

        if (logger_ && !warned_about_placeholder_) {
            warned_about_placeholder_ = true;
            logger_->Info(
                "Live player capture bound to the xOBSE runtime layout. Combat hooks "
                "and remote proxy application are still pending."
            );
        }

        return true;
    }

    void ApplyRemotePlayerState(const RemotePlayerState& state) override {
        RuntimePlayerCharacter* const runtime_player = GetPlayerCharacter();
        auto* const player = reinterpret_cast<PlayerCharacter*>(runtime_player);
        if (player == nullptr || player->parentCell == nullptr) {
            return;
        }

        if (console_ == nullptr || console_->RunScriptLine2 == nullptr) {
            if (logger_ && !warned_about_missing_console_) {
                warned_about_missing_console_ = true;
                logger_->Error("Remote proxy updates are blocked because the xOBSE console interface is unavailable");
            }
            return;
        }

        RemoteProxy& proxy = remote_proxies_[state.sender];
        if (proxy.has_target_state && state.timestamp < proxy.last_timestamp) {
            return;
        }
        proxy.last_cell = state.cell;
        proxy.last_timestamp = state.timestamp;
        proxy.target_state = state;
        proxy.has_target_state = true;

        if (state.cell != DescribeCell(runtime_player->parent_cell)) {
            ParkRemoteProxy(proxy);
            return;
        }

        if (proxy.reference == nullptr || proxy.reference->parentCell != player->parentCell) {
            proxy.reference = SpawnRemoteProxy(player);
            if (proxy.reference == nullptr) {
                return;
            }
            SnapProxyToState(*proxy.reference, state);
        }

        ApplyProxyProfile(proxy, state);
        ApplyProxyVitals(proxy, state);
        SyncProxyEquipment(proxy, state);
        SyncProxyCombat(proxy, state);

        if (logger_ && !announced_remote_peer_) {
            announced_remote_peer_ = true;
            logger_->Info("Remote proxy spawning is active for in-cell peers");
        }
    }

    void ApplyRemoteAnimationEvent(const RemoteAnimationEvent& event) override {
        auto it = remote_proxies_.find(event.sender);
        if (it == remote_proxies_.end() || it->second.reference == nullptr) {
            return;
        }

        if (it->second.last_animation_group == event.group) {
            return;
        }

        std::ostringstream command;
        command << "PlayGroup " << event.group << ' ' << (event.loop ? 1 : 0);
        if (RunConsoleCommand(command.str(), it->second.reference)) {
            it->second.last_animation_group = event.group;
        }
    }

    void ApplyRemoteCombatEvent(const RemoteCombatEvent& event) override {
        if (event.kind == "enter_combat" || event.kind == "leave_combat") {
            auto it = remote_proxies_.find(event.sender);
            if (it == remote_proxies_.end() || it->second.reference == nullptr) {
                return;
            }

            std::ostringstream command;
            command << "SetAlert " << (event.kind == "enter_combat" ? 1 : 0);
            RunConsoleCommand(command.str(), it->second.reference);
            if (event.kind == "enter_combat" && !event.targetRefId.empty()) {
                std::ostringstream engage_command;
                engage_command << "StartCombat " << event.targetRefId;
                RunConsoleCommand(engage_command.str(), it->second.reference);
            }
            return;
        }

        const std::uint32_t target_id = ParseFormId(event.targetRefId);
        if (target_id == 0) {
            return;
        }

        TESForm* const target_form = LookupRuntimeFormById(target_id);
        auto* const target_actor = dynamic_cast<Actor*>(reinterpret_cast<TESObjectREFR*>(target_form));
        if (target_actor == nullptr || event.damage <= 0.0f) {
            return;
        }

        target_actor->DamageAV_F(kActorVal_Health, event.damage, nullptr);
    }

    void ApplyRemoteQuestState(const RemoteQuestState& state) override {
        RuntimePlayerCharacter* const runtime_player = GetPlayerCharacter();
        auto* const player = reinterpret_cast<PlayerCharacter*>(runtime_player);
        if (player == nullptr) {
            return;
        }

        const auto previous_timestamp = applied_quest_timestamps_.find(state.questId);
        if (previous_timestamp != applied_quest_timestamps_.end() && state.timestamp <= previous_timestamp->second) {
            return;
        }

        auto existing_stage = applied_quest_stages_.find(state.questId);
        if (existing_stage != applied_quest_stages_.end() && state.stage < existing_stage->second) {
            return;
        }

        if (state.status == "running" || state.status == "started") {
            std::ostringstream start_command;
            start_command << "StartQuest " << state.questId;
            RunConsoleCommand(start_command.str(), player);
        } else if (state.status == "stopped") {
            std::ostringstream stop_command;
            stop_command << "StopQuest " << state.questId;
            RunConsoleCommand(stop_command.str(), player);
        }

        std::ostringstream command;
        command << "SetStage " << state.questId << ' ' << state.stage;
        if (RunConsoleCommand(command.str(), player)) {
            applied_quest_stages_[state.questId] = state.stage;
            if (logger_) {
                logger_->Info("Applied quest stage " + state.questId + " -> " + std::to_string(state.stage));
            }
        }

        if (state.makeActive) {
            std::ostringstream active_command;
            active_command << "SetActiveQuest " << state.questId;
            RunConsoleCommand(active_command.str(), player);
        }

        if (state.objectiveIndex >= 0) {
            std::ostringstream objective_command;
            objective_command << "SetObjectiveDisplayed " << state.questId << ' ' << state.objectiveIndex << ' '
                              << (state.objectiveDisplayed ? 1 : 0);
            RunConsoleCommand(objective_command.str(), player);

            std::ostringstream completed_command;
            completed_command << "SetObjectiveCompleted " << state.questId << ' ' << state.objectiveIndex << ' '
                              << (state.objectiveCompleted ? 1 : 0);
            RunConsoleCommand(completed_command.str(), player);
        }

        if (!state.scriptLine.empty()) {
            RunConsoleCommand(state.scriptLine, player);
        }

        if (state.completed) {
            std::ostringstream complete_command;
            complete_command << "CompleteQuest " << state.questId;
            RunConsoleCommand(complete_command.str(), player);
        }

        if (state.failed) {
            std::ostringstream fail_command;
            fail_command << "FailQuest " << state.questId;
            RunConsoleCommand(fail_command.str(), player);
        }

        applied_quest_timestamps_[state.questId] = state.timestamp;
    }

    void ApplyRemoteLootState(const RemoteLootState& state) override {
        RuntimePlayerCharacter* const runtime_player = GetPlayerCharacter();
        auto* const player = reinterpret_cast<PlayerCharacter*>(runtime_player);
        if (player == nullptr) {
            return;
        }

        const auto previous_timestamp = applied_loot_timestamps_.find(state.lootId);
        if (previous_timestamp != applied_loot_timestamps_.end() && state.timestamp <= previous_timestamp->second) {
            return;
        }

        TESObjectREFR* target_reference = player;
        if (!state.containerRefId.empty()) {
            TESForm* const container_form = LookupRuntimeFormById(ParseFormId(state.containerRefId));
            auto* const container_reference = reinterpret_cast<TESObjectREFR*>(container_form);
            if (container_reference != nullptr) {
                target_reference = container_reference;
            }
        }

        if (!state.itemRefId.empty() && (state.removed || state.action == "picked_up" || state.action == "despawn")) {
            TESForm* const item_form = LookupRuntimeFormById(ParseFormId(state.itemRefId));
            auto* const item_reference = reinterpret_cast<TESObjectREFR*>(item_form);
            if (item_reference != nullptr) {
                RunConsoleCommand("Disable", item_reference);
            }
        }

        if (state.isWorldObject && state.hasTransform && state.containerRefId.empty()) {
            ApplyWorldLootState(*player, state);
            applied_loot_timestamps_[state.lootId] = state.timestamp;
            return;
        }

        std::ostringstream command;
        if (state.removed || state.action == "remove" || state.action == "despawn" || state.action == "picked_up") {
            command << "RemoveItem " << state.formId << ' ' << state.count;
        } else {
            command << "AddItem " << state.formId << ' ' << state.count;
        }

        if (RunConsoleCommand(command.str(), target_reference)) {
            applied_loot_timestamps_[state.lootId] = state.timestamp;
            if (logger_) {
                logger_->Info("Applied loot state " + state.lootId + " via " + state.action);
            }
        }
    }

    void RemoveRemotePlayer(const std::string& sender) override {
        auto it = remote_proxies_.find(sender);
        if (it == remote_proxies_.end()) {
            return;
        }

        ParkRemoteProxy(it->second);
        remote_proxies_.erase(it);
    }

    void ResetWorldState() override {
        for (auto& [sender, proxy] : remote_proxies_) {
            if (proxy.reference != nullptr) {
                RunConsoleCommand("Disable", proxy.reference);
            }
        }
        remote_proxies_.clear();
        applied_quest_stages_.clear();
        applied_quest_timestamps_.clear();
        applied_loot_timestamps_.clear();
        tracked_world_loot_refs_.clear();
    }

    void Update() override {
        RuntimePlayerCharacter* const runtime_player = GetPlayerCharacter();
        auto* const player = reinterpret_cast<PlayerCharacter*>(runtime_player);
        if (player == nullptr || player->parentCell == nullptr) {
            return;
        }

        const std::int64_t now = GetNowMs();
        std::vector<std::string> expired;

        for (auto& [sender, proxy] : remote_proxies_) {
            if (!proxy.has_target_state || now - proxy.last_timestamp > kProxyStaleAfterMs) {
                ParkRemoteProxy(proxy);
                expired.push_back(sender);
                continue;
            }

            if (proxy.target_state.cell != DescribeCell(runtime_player->parent_cell)) {
                ParkRemoteProxy(proxy);
                continue;
            }

            if (proxy.reference == nullptr || proxy.reference->parentCell != player->parentCell) {
                proxy.reference = SpawnRemoteProxy(player);
                if (proxy.reference == nullptr) {
                    continue;
                }
                SnapProxyToState(*proxy.reference, proxy.target_state);
            }

            ApplyProxyProfile(proxy, proxy.target_state);
            ApplyProxyVitals(proxy, proxy.target_state);
            SyncProxyEquipment(proxy, proxy.target_state);
            SyncProxyCombat(proxy, proxy.target_state);
            SmoothProxyTowardState(*proxy.reference, proxy.target_state);
        }

        for (const std::string& sender : expired) {
            RemoveRemotePlayer(sender);
        }
    }

  private:
    struct RemoteProxy {
        TESObjectREFR* reference = nullptr;
        std::string last_cell;
        std::int64_t last_timestamp = 0;
        RemotePlayerState target_state{};
        bool has_target_state = false;
        std::string engaged_target_ref_id;
        std::string last_animation_group;
        CharacterProfile applied_profile{};
        std::string equipped_weapon_form_id;
        float last_health = -1.0f;
        float last_magicka = -1.0f;
        float last_stamina = -1.0f;
    };

    static std::int64_t GetNowMs() {
        using namespace std::chrono;
        return duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count();
    }

    static std::string FormatFormId(const TESForm* form) {
        if (form == nullptr) {
            return "00000000";
        }

        std::ostringstream stream;
        stream << std::uppercase << std::hex << std::setw(8) << std::setfill('0') << form->refID;
        return stream.str();
    }

    static float ToDegrees(float radians) {
        return radians * kRadiansToDegrees;
    }

    std::set<UInt32> SnapshotCellReferenceIds(const TESObjectCELL* cell) const {
        std::set<UInt32> ids;
        if (cell == nullptr) {
            return ids;
        }

        for (auto* entry = cell->objectList.next; entry != nullptr; entry = entry->next) {
            if (entry->refr != nullptr) {
                ids.insert(entry->refr->refID);
            }
        }
        return ids;
    }

    TESObjectREFR* FindNewlySpawnedReference(
        TESObjectCELL* cell,
        const std::set<UInt32>& before_ids,
        const TESForm* expected_base_form,
        const TESObjectREFR* player
    ) const {
        if (cell == nullptr) {
            return nullptr;
        }

        for (auto* entry = cell->objectList.next; entry != nullptr; entry = entry->next) {
            TESObjectREFR* const reference = entry->refr;
            if (reference == nullptr || reference == player) {
                continue;
            }

            if (before_ids.contains(reference->refID)) {
                continue;
            }

            if (reference->baseForm == expected_base_form) {
                return reference;
            }
        }

        return nullptr;
    }

    bool RunConsoleCommand(const std::string& command, TESObjectREFR* calling_reference) const {
        return console_ != nullptr
            && console_->RunScriptLine2 != nullptr
            && console_->RunScriptLine2(command.c_str(), calling_reference, true);
    }

    void ParkRemoteProxy(RemoteProxy& proxy) {
        if (proxy.reference != nullptr) {
            RunConsoleCommand("Disable", proxy.reference);
            proxy.reference = nullptr;
        }
        proxy.engaged_target_ref_id.clear();
        proxy.last_animation_group.clear();
        proxy.equipped_weapon_form_id.clear();
        proxy.applied_profile = {};
    }

    TESObjectREFR* SpawnRemoteProxy(PlayerCharacter* player) {
        TESForm* const base_form = player->GetBaseForm();
        if (base_form == nullptr || player->parentCell == nullptr) {
            return nullptr;
        }

        const std::set<UInt32> before_ids = SnapshotCellReferenceIds(player->parentCell);

        std::ostringstream command;
        command << "PlaceAtMe " << FormatFormId(base_form) << " 1 0 0";
        if (!RunConsoleCommand(command.str(), player)) {
            if (logger_) {
                logger_->Error("Failed to issue PlaceAtMe for remote proxy spawn");
            }
            return nullptr;
        }

        TESObjectREFR* const proxy = FindNewlySpawnedReference(
            player->parentCell,
            before_ids,
            base_form,
            player
        );
        if (proxy == nullptr) {
            if (logger_) {
                logger_->Error("Remote proxy spawn command succeeded but no new reference was discovered in the current cell");
            }
            return nullptr;
        }

        RunConsoleCommand("SetGhost 1", proxy);
        RunConsoleCommand("SetRestrained 1", proxy);
        RunConsoleCommand("SetAV Speed 0", proxy);
        return proxy;
    }

    void ApplyProxyTransform(TESObjectREFR& proxy, const Vec3& position, const Vec3& rotation) {
        auto send_axis_command = [this, &proxy](const char* command_name, char axis, float value) {
            std::ostringstream command;
            command << command_name << ' ' << axis << ' ' << value;
            RunConsoleCommand(command.str(), &proxy);
        };

        send_axis_command("SetPos_T", 'x', position.x);
        send_axis_command("SetPos_T", 'y', position.y);
        send_axis_command("SetPos_T", 'z', position.z);
        send_axis_command("SetAngle", 'x', ToDegrees(rotation.x));
        send_axis_command("SetAngle", 'y', ToDegrees(rotation.y));
        send_axis_command("SetAngle", 'z', ToDegrees(rotation.z));
    }

    void ApplyProxyVitals(RemoteProxy& proxy, const RemotePlayerState& state) {
        if (proxy.reference == nullptr) {
            return;
        }

        auto maybe_set_av = [this, &proxy](const char* name, float value) {
            std::ostringstream command;
            command << "SetAV " << name << ' ' << ClampNonNegative(value);
            RunConsoleCommand(command.str(), proxy.reference);
        };

        if (proxy.last_health < 0.0f || AxisDistance(proxy.last_health, state.health) >= kHealthDesyncTolerance) {
            maybe_set_av("Health", state.health);
            proxy.last_health = state.health;
        }

        if (proxy.last_magicka < 0.0f || AxisDistance(proxy.last_magicka, state.magicka) >= kMagickaDesyncTolerance) {
            maybe_set_av("Magicka", state.magicka);
            proxy.last_magicka = state.magicka;
        }

        if (proxy.last_stamina < 0.0f || AxisDistance(proxy.last_stamina, state.stamina) >= kStaminaDesyncTolerance) {
            maybe_set_av("Fatigue", state.stamina);
            proxy.last_stamina = state.stamina;
        }
    }

    void ApplyProxyProfile(RemoteProxy& proxy, const RemotePlayerState& state) {
        if (proxy.reference == nullptr) {
            return;
        }

        const CharacterProfile& profile = state.profile;
        if (!profile.characterName.empty()
            && profile.characterName != proxy.applied_profile.characterName) {
            std::ostringstream command;
            command << "SetName " << QuoteConsoleString(profile.characterName);
            if (RunConsoleCommand(command.str(), proxy.reference)) {
                proxy.applied_profile.characterName = profile.characterName;
            }
        }

        if (!profile.hairFormId.empty()
            && profile.hairFormId != proxy.applied_profile.hairFormId) {
            std::ostringstream command;
            command << "SetHair " << profile.hairFormId;
            if (RunConsoleCommand(command.str(), proxy.reference)) {
                proxy.applied_profile.hairFormId = profile.hairFormId;
                proxy.applied_profile.hairName = profile.hairName;
            }
        }

        if (!profile.eyesFormId.empty()
            && profile.eyesFormId != proxy.applied_profile.eyesFormId) {
            std::ostringstream command;
            command << "SetEyes " << profile.eyesFormId;
            if (RunConsoleCommand(command.str(), proxy.reference)) {
                proxy.applied_profile.eyesFormId = profile.eyesFormId;
                proxy.applied_profile.eyesName = profile.eyesName;
            }
        }

        if (AxisDistance(proxy.applied_profile.scale, profile.scale) > 0.01f) {
            std::ostringstream command;
            command << "SetScale " << profile.scale;
            if (RunConsoleCommand(command.str(), proxy.reference)) {
                proxy.applied_profile.scale = profile.scale;
            }
        }

        proxy.applied_profile.classFormId = profile.classFormId;
        proxy.applied_profile.className = profile.className;
        proxy.applied_profile.raceFormId = profile.raceFormId;
        proxy.applied_profile.raceName = profile.raceName;
        proxy.applied_profile.birthsignFormId = profile.birthsignFormId;
        proxy.applied_profile.birthsignName = profile.birthsignName;
        proxy.applied_profile.isFemale = profile.isFemale;
        proxy.applied_profile.hairColorR = profile.hairColorR;
        proxy.applied_profile.hairColorG = profile.hairColorG;
        proxy.applied_profile.hairColorB = profile.hairColorB;
    }

    void SyncProxyEquipment(RemoteProxy& proxy, const RemotePlayerState& state) {
        if (proxy.reference == nullptr || state.equippedWeaponFormId == proxy.equipped_weapon_form_id) {
            return;
        }

        if (!proxy.equipped_weapon_form_id.empty()) {
            std::ostringstream unequip_command;
            unequip_command << "UnequipItemSilent " << proxy.equipped_weapon_form_id << " 1";
            RunConsoleCommand(unequip_command.str(), proxy.reference);
        }

        proxy.equipped_weapon_form_id = state.equippedWeaponFormId;
        if (proxy.equipped_weapon_form_id.empty()) {
            return;
        }

        std::ostringstream add_command;
        add_command << "AddItem " << proxy.equipped_weapon_form_id << " 1";
        RunConsoleCommand(add_command.str(), proxy.reference);

        std::ostringstream equip_command;
        equip_command << "EquipItemSilent " << proxy.equipped_weapon_form_id << " 1";
        RunConsoleCommand(equip_command.str(), proxy.reference);
    }

    void SyncProxyCombat(RemoteProxy& proxy, const RemotePlayerState& state) {
        if (proxy.reference == nullptr) {
            return;
        }

        std::ostringstream command;
        command << "SetAlert " << (state.isInCombat ? 1 : 0);
        RunConsoleCommand(command.str(), proxy.reference);

        if (state.isInCombat && !state.combatTargetRefId.empty() && state.combatTargetRefId != proxy.engaged_target_ref_id) {
            std::ostringstream engage_command;
            engage_command << "StartCombat " << state.combatTargetRefId;
            if (RunConsoleCommand(engage_command.str(), proxy.reference)) {
                proxy.engaged_target_ref_id = state.combatTargetRefId;
            }
        }

        if (!state.isInCombat) {
            proxy.engaged_target_ref_id.clear();
        }
    }

    void ApplyWorldLootState(PlayerCharacter& player, const RemoteLootState& state) {
        TESObjectREFR* loot_reference = nullptr;
        auto tracked = tracked_world_loot_refs_.find(state.lootId);
        if (tracked != tracked_world_loot_refs_.end()) {
            loot_reference = reinterpret_cast<TESObjectREFR*>(LookupRuntimeFormById(tracked->second));
        }

        if (state.removed || state.action == "remove" || state.action == "despawn" || state.action == "picked_up") {
            if (loot_reference != nullptr) {
                RunConsoleCommand("Disable", loot_reference);
            }
            if (!state.itemRefId.empty()) {
                TESForm* const item_form = LookupRuntimeFormById(ParseFormId(state.itemRefId));
                auto* const item_reference = reinterpret_cast<TESObjectREFR*>(item_form);
                if (item_reference != nullptr) {
                    RunConsoleCommand("Disable", item_reference);
                }
            }
            tracked_world_loot_refs_.erase(state.lootId);
            return;
        }

        if (loot_reference == nullptr) {
            const std::uint32_t form_id = ParseFormId(state.formId);
            TESForm* const base_form = LookupRuntimeFormById(form_id);
            if (base_form == nullptr || player.parentCell == nullptr) {
                return;
            }

            const std::set<UInt32> before_ids = SnapshotCellReferenceIds(player.parentCell);
            std::ostringstream command;
            command << "PlaceAtMe " << FormatFormId(base_form) << ' ' << state.count << " 0 0";
            if (!RunConsoleCommand(command.str(), &player)) {
                return;
            }

            loot_reference = FindNewlySpawnedReference(player.parentCell, before_ids, base_form, &player);
            if (loot_reference == nullptr) {
                return;
            }

            tracked_world_loot_refs_[state.lootId] = loot_reference->refID;
        }

        if (!state.cell.empty() && state.cell != DescribeCell(reinterpret_cast<RuntimePlayerCharacter*>(&player)->parent_cell)) {
            return;
        }

        ApplyProxyTransform(*loot_reference, state.position, state.rotation);
    }

    void SnapProxyToState(TESObjectREFR& proxy, const RemotePlayerState& state) {
        ApplyProxyTransform(proxy, state.position, state.rotation);
    }

    void SmoothProxyTowardState(TESObjectREFR& proxy, const RemotePlayerState& state) {
        const bool should_snap = AxisDistance(proxy.posX, state.position.x) > kSnapDistance
            || AxisDistance(proxy.posY, state.position.y) > kSnapDistance
            || AxisDistance(proxy.posZ, state.position.z) > kSnapDistance;

        if (should_snap) {
            SnapProxyToState(proxy, state);
            return;
        }

        Vec3 blended_position{
            Lerp(proxy.posX, state.position.x, kProxySmoothingFactor),
            Lerp(proxy.posY, state.position.y, kProxySmoothingFactor),
            Lerp(proxy.posZ, state.position.z, kProxySmoothingFactor),
        };

        Vec3 blended_rotation{
            Lerp(proxy.rotX, state.rotation.x, kProxySmoothingFactor),
            Lerp(proxy.rotY, state.rotation.y, kProxySmoothingFactor),
            Lerp(proxy.rotZ, state.rotation.z, kProxySmoothingFactor),
        };

        ApplyProxyTransform(proxy, blended_position, blended_rotation);
    }

    std::shared_ptr<Logger> logger_;
    OBSEConsoleInterface* console_ = nullptr;
    std::map<std::string, RemoteProxy> remote_proxies_;
    std::map<std::string, std::int32_t> applied_quest_stages_;
    std::map<std::string, std::int64_t> applied_quest_timestamps_;
    std::map<std::string, std::int64_t> applied_loot_timestamps_;
    std::map<std::string, UInt32> tracked_world_loot_refs_;
    bool warned_about_placeholder_ = false;
    bool warned_about_missing_console_ = false;
    bool announced_remote_peer_;
};

}  // namespace

std::unique_ptr<GameAdapter> CreateGameAdapter(
    std::shared_ptr<Logger> logger,
    OBSEConsoleInterface* console
) {
    return std::make_unique<RuntimeBackedGameAdapter>(std::move(logger), console);
}

}  // namespace pseudo_onblivion

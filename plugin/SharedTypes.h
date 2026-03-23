#pragma once

#include <cstdint>
#include <string>

namespace pseudo_onblivion {

struct Vec3 {
    float x;
    float y;
    float z;
};

struct CharacterProfile {
    std::string characterName;
    std::string raceFormId;
    std::string raceName;
    std::string classFormId;
    std::string className;
    std::string birthsignFormId;
    std::string birthsignName;
    std::string hairFormId;
    std::string hairName;
    std::string eyesFormId;
    std::string eyesName;
    bool isFemale = false;
    float scale = 1.0f;
    std::int32_t hairColorR = 0;
    std::int32_t hairColorG = 0;
    std::int32_t hairColorB = 0;
};

struct PlayerSnapshot {
    Vec3 position;
    Vec3 rotation;
    std::string cell;
    float health;
    float magicka;
    float stamina;
    std::string equippedWeaponFormId;
    std::string combatTargetRefId;
    bool isInCombat;
    CharacterProfile profile;
};

struct RemotePlayerState {
    std::string sender;
    std::string cell;
    Vec3 position;
    Vec3 rotation;
    float health;
    float magicka;
    float stamina;
    std::string equippedWeaponFormId;
    std::string combatTargetRefId;
    bool isInCombat;
    std::int64_t timestamp;
    CharacterProfile profile;
};

struct RemoteQuestState {
    std::string sender;
    std::string questId;
    std::string status;
    std::int32_t stage;
    std::int32_t objectiveIndex;
    bool objectiveCompleted;
    bool objectiveDisplayed;
    bool completed;
    bool failed;
    bool makeActive;
    std::string scriptLine;
    std::int64_t timestamp;
};

struct RemoteLootState {
    std::string sender;
    std::string lootId;
    std::string action;
    std::string formId;
    std::string containerRefId;
    std::string itemRefId;
    std::string cell;
    Vec3 position{};
    Vec3 rotation{};
    bool hasTransform = false;
    bool isWorldObject = false;
    std::int32_t count;
    bool removed;
    std::int64_t timestamp;
};

struct RemoteAnimationEvent {
    std::string sender;
    std::string group;
    bool loop;
    std::int64_t timestamp;
};

struct RemoteCombatEvent {
    std::string sender;
    std::string kind;
    std::string targetRefId;
    std::string weaponFormId;
    float damage;
    std::int64_t timestamp;
};

}  // namespace pseudo_onblivion

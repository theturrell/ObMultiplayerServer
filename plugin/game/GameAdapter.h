#pragma once

#include "../SharedTypes.h"
#include "../logging/Logger.h"

#include <memory>

struct OBSEConsoleInterface;

namespace pseudo_onblivion {

class GameAdapter {
  public:
    virtual ~GameAdapter() = default;

    virtual bool CaptureLocalPlayerSnapshot(PlayerSnapshot& snapshot) = 0;
    virtual void ApplyRemotePlayerState(const RemotePlayerState& state) = 0;
    virtual void ApplyRemoteAnimationEvent(const RemoteAnimationEvent& event) = 0;
    virtual void ApplyRemoteCombatEvent(const RemoteCombatEvent& event) = 0;
    virtual void ApplyRemoteQuestState(const RemoteQuestState& state) = 0;
    virtual void ApplyRemoteLootState(const RemoteLootState& state) = 0;
    virtual void RemoveRemotePlayer(const std::string& sender) = 0;
    virtual void ResetWorldState() = 0;
    virtual void Update() = 0;
};

std::unique_ptr<GameAdapter> CreateGameAdapter(
    std::shared_ptr<Logger> logger,
    ::OBSEConsoleInterface* console = nullptr
);

}  // namespace pseudo_onblivion

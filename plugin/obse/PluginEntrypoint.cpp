#include "../PseudoOnBlivionPlugin.h"
#include "../config/PluginConfig.h"
#include "../logging/Logger.h"
#include "IPrefix.h"
#include <map>
#include <type_traits>
#include "obse/PluginAPI.h"
#include "obse_common/obse_version.h"

#include <Windows.h>

#include <memory>
#include <string>

namespace pseudo_onblivion {

namespace {

std::unique_ptr<PseudoOnBlivionPlugin> g_plugin;
HMODULE g_module = nullptr;
std::shared_ptr<Logger> g_logger;
PluginHandle g_plugin_handle = kPluginHandle_Invalid;
OBSEMessagingInterface* g_messaging = nullptr;
OBSETasks2Interface* g_tasks2 = nullptr;
OBSEConsoleInterface* g_console = nullptr;
Task<bool>* g_pump_task = nullptr;

static const char* const kPluginName = "PseudoOnBlivion";
static const UInt32 kPluginVersion = 1;

std::string GetModulePath() {
    char buffer[MAX_PATH]{};
    const DWORD length = GetModuleFileNameA(g_module, buffer, MAX_PATH);
    if (length == 0 || length == MAX_PATH) {
        return std::string();
    }
    return std::string(buffer, length);
}

std::string GetModuleDirectory() {
    const std::string module_path = GetModulePath();
    if (module_path.empty()) {
        return ".";
    }
    const std::string::size_type slash = module_path.find_last_of("\\/");
    if (slash == std::string::npos) {
        return ".";
    }
    return module_path.substr(0, slash);
}

std::string ResolvePluginPath(const std::string& leaf_name) {
    return GetModuleDirectory() + "\\" + leaf_name;
}

PluginConfig LoadRuntimeConfig() {
    const std::string ini_path = ResolvePluginPath("PseudoOnBlivion.ini");
    PluginConfig config = LoadPluginConfig(ini_path);

    if (config.log_path.find(':') == std::string::npos
        && !(config.log_path.size() >= 2 && config.log_path[0] == '\\' && config.log_path[1] == '\\')) {
        config.log_path = ResolvePluginPath(config.log_path);
    }

    return config;
}

bool BootstrapPlugin() {
    const PluginConfig config = LoadRuntimeConfig();
    g_logger = std::make_shared<Logger>(config.log_path);
    NetworkClient client;
    std::unique_ptr<GameAdapter> game_adapter = CreateGameAdapter(g_logger, g_console);

    g_plugin = std::make_unique<PseudoOnBlivionPlugin>(
        std::move(client),
        config,
        std::move(game_adapter),
        g_logger
    );

    if (!g_plugin->Initialize()) {
        g_logger->Error("Plugin initialization failed");
        g_plugin.reset();
        return false;
    }

    g_plugin->Start();
    g_logger->Info("Plugin background workers started");
    return true;
}

void ShutdownPlugin() {
    if (g_tasks2 && g_pump_task) {
        g_tasks2->RemoveTaskRemovable(g_pump_task);
        g_pump_task = nullptr;
    }
    if (g_plugin) {
        g_plugin->Stop();
        g_plugin.reset();
    }
    g_logger.reset();
}

bool PumpPluginOnGameThread() {
    if (g_plugin) {
        g_plugin->PumpGameThreadWork();
    }
    return false;
}

void OnObseMessage(OBSEMessagingInterface::Message* message) {
    if (!g_logger || !message) {
        return;
    }

    switch (message->type) {
    case OBSEMessagingInterface::kMessage_PostLoad:
        g_logger->Info("Received xOBSE PostLoad message");
        break;
    case OBSEMessagingInterface::kMessage_ExitGame:
        g_logger->Info("Received xOBSE ExitGame message");
        if (g_plugin) {
            g_plugin->ResetSessionState();
        }
        break;
    case OBSEMessagingInterface::kMessage_ExitToMainMenu:
        g_logger->Info("Received xOBSE ExitToMainMenu message");
        if (g_plugin) {
            g_plugin->ResetSessionState();
        }
        break;
    case OBSEMessagingInterface::kMessage_LoadGame:
        g_logger->Info("Received xOBSE LoadGame message");
        if (g_plugin) {
            g_plugin->ResetSessionState();
        }
        break;
    case OBSEMessagingInterface::kMessage_PostPostLoad:
        g_logger->Info("Received xOBSE PostPostLoad message");
        break;
    case OBSEMessagingInterface::kMessage_GameInitialized:
        g_logger->Info("Received xOBSE GameInitialized message");
        if (g_plugin) {
            g_plugin->ResetSessionState();
        }
        break;
    default:
        g_logger->Debug("Received xOBSE message type " + std::to_string(message->type));
        break;
    }
}

}  // namespace

extern "C" __declspec(dllexport) bool OBSEPlugin_Query(
    const OBSEInterface* obse,
    PluginInfo* info
) {
    if (info != nullptr) {
        info->infoVersion = PluginInfo::kInfoVersion;
        info->name = kPluginName;
        info->version = kPluginVersion;
    }

    if (obse == nullptr) {
        return false;
    }

    if (obse->isEditor != 0) {
        return false;
    }

    if (obse->obseVersion < OBSE_VERSION_INTEGER) {
        return false;
    }

    if (obse->oblivionVersion != OBLIVION_VERSION) {
        return false;
    }

    return true;
}

extern "C" __declspec(dllexport) bool OBSEPlugin_Load(const OBSEInterface* obse) {
    if (obse == nullptr) {
        return false;
    }

    g_plugin_handle = obse->GetPluginHandle ? obse->GetPluginHandle() : kPluginHandle_Invalid;
    g_console = static_cast<OBSEConsoleInterface*>(obse->QueryInterface(kInterface_Console));
    g_messaging = static_cast<OBSEMessagingInterface*>(obse->QueryInterface(kInterface_Messaging));
    g_tasks2 = static_cast<OBSETasks2Interface*>(obse->QueryInterface(kInterface_Tasks2));

    if (!BootstrapPlugin()) {
        return false;
    }

    if (g_logger) {
        g_logger->Info("xOBSE plugin load entrypoint reached");
        if (g_plugin_handle != kPluginHandle_Invalid) {
            g_logger->Info("Assigned plugin handle");
        }
    }

    if (g_messaging && g_plugin_handle != kPluginHandle_Invalid) {
        g_messaging->RegisterListener(g_plugin_handle, "OBSE", OnObseMessage);
    }

    if (g_tasks2 && !g_pump_task) {
        g_pump_task = g_tasks2->EnqueueTaskRemovable(PumpPluginOnGameThread);
        if (g_logger) {
            g_logger->Info("Registered recurring game-thread pump task");
        }
    }

    return true;
}

extern "C" __declspec(dllexport) bool PseudoOnBlivion_InitializeStandalone() {
    return BootstrapPlugin();
}

extern "C" __declspec(dllexport) void PseudoOnBlivion_ShutdownStandalone() {
    ShutdownPlugin();
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID /*reserved*/) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_module = module;
        DisableThreadLibraryCalls(module);
    } else if (reason == DLL_PROCESS_DETACH) {
        ShutdownPlugin();
    }

    return TRUE;
}

}  // namespace pseudo_onblivion

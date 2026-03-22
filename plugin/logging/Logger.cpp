#include "Logger.h"

#include <chrono>
#include <iomanip>
#include <sstream>

namespace pseudo_onblivion {

namespace {

std::string Timestamp() {
    const auto now = std::chrono::system_clock::now();
    const auto time = std::chrono::system_clock::to_time_t(now);
    std::tm local_time{};
    localtime_s(&local_time, &time);

    std::ostringstream out;
    out << std::put_time(&local_time, "%Y-%m-%d %H:%M:%S");
    return out.str();
}

}  // namespace

Logger::Logger(const std::string& path) : output_(path, std::ios::app) {}

void Logger::Debug(const std::string& message) {
    Write("DEBUG", message);
}

void Logger::Info(const std::string& message) {
    Write("INFO", message);
}

void Logger::Error(const std::string& message) {
    Write("ERROR", message);
}

void Logger::Write(const char* level, const std::string& message) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!output_) {
        return;
    }
    output_ << "[" << Timestamp() << "] [" << level << "] " << message << "\n";
    output_.flush();
}

}  // namespace pseudo_onblivion

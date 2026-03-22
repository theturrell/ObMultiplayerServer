#pragma once

#include <fstream>
#include <mutex>
#include <string>

namespace pseudo_onblivion {

class Logger {
  public:
    explicit Logger(const std::string& path);

    void Debug(const std::string& message);
    void Info(const std::string& message);
    void Error(const std::string& message);

  private:
    void Write(const char* level, const std::string& message);

    std::mutex mutex_;
    std::ofstream output_;
};

}  // namespace pseudo_onblivion

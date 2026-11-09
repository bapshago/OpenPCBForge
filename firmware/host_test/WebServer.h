// Fake WebServer for the host test: the test calls a route with form fields and
// optional login, and reads the reply.
#pragma once
#include <map>
#include <string>
#include <cstdint>
enum HTTPMethod { HTTP_GET, HTTP_POST };
enum { UPLOAD_FILE_START, UPLOAD_FILE_WRITE, UPLOAD_FILE_END, UPLOAD_FILE_ABORTED };
struct HTTPUpload { int status; std::string filename; uint8_t buf[64]; size_t currentSize; };
struct WebServer {
  std::map<std::pair<std::string, int>, void (*)()> routes;
  std::map<std::string, std::string> args;
  std::string user, pass;          // credentials the "browser" sends
  int code = 0; std::string type, body; bool authRequested = false; bool running = false;
  HTTPUpload up{};
  explicit WebServer(int) {}
  void on(const char *path, HTTPMethod m, void (*fn)()) { routes[{path, m}] = fn; }
  void on(const char *path, HTTPMethod m, void (*fn)(), void (*)()) { routes[{path, m}] = fn; }
  void begin() { running = true; }
  void stop() { running = false; }
  void handleClient() {}
  std::string arg(const char *name) { auto it = args.find(name); return it == args.end() ? "" : it->second; }
  bool authenticate(const char *u, const char *p) { return user == u && pass == p; }
  void requestAuthentication() { authRequested = true; code = 401; body.clear(); }
  HTTPUpload &upload() { return up; }
  void send(int c, const char *t, const char *b) { code = c; type = t; body = b; }
  bool request(const std::string &path, HTTPMethod m = HTTP_GET) {
    auto it = routes.find({path, m}); if (it == routes.end()) return false;
    authRequested = false; code = 0; it->second(); return true;
  }
};

// Minimal stand-in for ESP-IDF's driver/twai.h, enough for the host test.
#pragma once
#include <stdint.h>
typedef int esp_err_t; typedef int gpio_num_t;
#define ESP_OK 0
#define ESP_FAIL -1
typedef enum {TWAI_MODE_NORMAL, TWAI_MODE_NO_ACK, TWAI_MODE_LISTEN_ONLY} twai_mode_t;
typedef enum {TWAI_STATE_STOPPED, TWAI_STATE_RUNNING, TWAI_STATE_BUS_OFF, TWAI_STATE_RECOVERING} twai_state_t;
typedef struct { twai_mode_t mode; int tx_queue_len, rx_queue_len; } twai_general_config_t;
typedef struct { int x; } twai_timing_config_t;
typedef struct { int x; } twai_filter_config_t;
typedef struct { twai_state_t state; uint32_t tx_error_counter; } twai_status_info_t;
typedef struct { uint32_t identifier; uint32_t extd, rtr, ss, self; uint8_t data_length_code; uint8_t data[8]; } twai_message_t;
#define TWAI_GENERAL_CONFIG_DEFAULT(a,b,c) twai_general_config_t{c,0,0}
#define TWAI_TIMING_CONFIG_500KBITS() twai_timing_config_t{0}
#define TWAI_FILTER_CONFIG_ACCEPT_ALL() twai_filter_config_t{0}
esp_err_t twai_driver_install(const twai_general_config_t*, const twai_timing_config_t*, const twai_filter_config_t*);
esp_err_t twai_start(); esp_err_t twai_initiate_recovery();
esp_err_t twai_get_status_info(twai_status_info_t*);
esp_err_t twai_transmit(const twai_message_t*, int);
esp_err_t twai_receive(twai_message_t*, int);

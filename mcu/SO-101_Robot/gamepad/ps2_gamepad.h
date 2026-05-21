#ifndef __PS2_GAMEPAD_H__
#define __PS2_GAMEPAD_H__

#include <stdint.h>

#define PS2_CLK_PIN   0
#define PS2_DAT_PIN   1
#define PS2_CMD_PIN   2
#define PS2_CS_PIN    3

void ps2_init(void);
uint8_t ps2_read_packet(uint8_t *data);

#endif

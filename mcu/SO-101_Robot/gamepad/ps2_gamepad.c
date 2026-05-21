#include "ps2_gamepad.h"
#include "timer.h"
#include "board.h"

// 影子寄存器：记住输出值
static uint32_t gpio_out_shadow = 0;

static inline void gpio_write(uint8_t pin, uint8_t val) {
    if(val) {
        gpio_out_shadow |= (1 << pin);
    } else {
        gpio_out_shadow &= ~(1 << pin);
    }
    REG_GPIO_0_DR = gpio_out_shadow;
}

static inline uint8_t gpio_read(uint8_t pin) {
    return (REG_GPIO_0_DR >> pin) & 1;
}

void ps2_init(void) {
    uint32_t tmp;

    // 1. 初始化影子寄存器
    gpio_out_shadow = REG_GPIO_0_DR;
    gpio_out_shadow |= ((1 << PS2_CLK_PIN) | (1 << PS2_CMD_PIN) | (1 << PS2_CS_PIN));
    REG_GPIO_0_DR = gpio_out_shadow;

    for(volatile int i = 0; i < 1000; i++);

    // 2. 配置方向
    tmp = REG_GPIO_0_DDR;
    tmp &= ~((1 << PS2_CLK_PIN) | (1 << PS2_CMD_PIN) | (1 << PS2_CS_PIN));
    tmp |= (1 << PS2_DAT_PIN);
    REG_GPIO_0_DDR = tmp;

    // 3. 上拉
    REG_GPIO_0_PUB |= (1 << PS2_DAT_PIN);
}

static uint8_t ps2_transfer(uint8_t cmd) {
    uint8_t res = 0;
    uint8_t ref;

    for(ref = 0x01; ref != 0x00; ref <<= 1) {
        if(ref & cmd) gpio_write(PS2_CMD_PIN, 1); else gpio_write(PS2_CMD_PIN, 0);
        delay_us(5);

        gpio_write(PS2_CLK_PIN, 0);
        delay_us(16);

        if(gpio_read(PS2_DAT_PIN)) res |= ref;

        gpio_write(PS2_CLK_PIN, 1);
        delay_us(16);
    }
    return res;
}

uint8_t ps2_read_packet(uint8_t *data) {
    const uint8_t cmd[9] = {0x01, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};

    gpio_write(PS2_CS_PIN, 1);
    delay_us(100);

    gpio_write(PS2_CS_PIN, 0);
    delay_us(50);

    for (int i = 0; i < 9; i++) {
        data[i] = ps2_transfer(cmd[i]);
    }

    gpio_write(PS2_CS_PIN, 1);
    delay_us(100);

    return (data[2] == 0x5A) ? 1 : 0;
}

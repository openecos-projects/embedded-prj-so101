deps_config := \
	/home/jinghanhui/.local/ecos-sdk/tools/kconfig/Kconfig

include/config/auto.conf: \
	$(deps_config)


$(deps_config): ;

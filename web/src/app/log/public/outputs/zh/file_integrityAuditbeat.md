### Auditbeat file_integrity简介

- &zwnj;**基本功能**&zwnj;
  - 文件变更监控

  - 文件元数据采集

  - 文件内容完整性校验

  - 目录递归监控

  - 实时事件输出

- &zwnj;**主要特点**&zwnj;
  - 安全审计利器

  - 跨平台支持

  - 高效、实时

  - 可配置性强

  - 与 Elastic Stack 无缝集成

  - 典型应用场景

### Auditbeat file_integrity 输出字段


|分组|字段名|描述|类型|
|--------|------|------|--------|
|内置字段|collect_type|采集类型|-|
|内置字段|collector|采集器|-|
|内置字段|instance_id|实例id|-|
|file.elf|file.elf.go_imports|Go 语言导入元素名称和类型列表|flattened|
|file.elf|file.elf.go_imports_names_entropy|从 Go 导入列表计算的 Shannon 熵|long|
|file.elf|file.elf.go_imports_names_var_entropy|Go 导入列表的 Shannon 熵方差|long|
|file.elf|file.elf.go_import_hash|ELF 文件中 Go 导入的哈希（排除标准库），可用于二进制指纹识别|keyword|
|file.elf|file.elf.go_stripped|是否为已剥离符号或混淆的 Go 可执行文件|boolean|
|file.elf|file.elf.imports_names_entropy|从导入元素名称和类型列表计算的 Shannon 熵|long|
|file.elf|file.elf.imports_names_var_entropy|导入元素名称和类型列表的 Shannon 熵方差|long|
|file.elf|file.elf.import_hash|ELF 文件导入的哈希（类似 Windows PE imphash）|keyword|
|file.elf|file.elf.sections.var_entropy|ELF 文件中 section 的 Shannon 熵方差|long|
|file.macho|file.macho.go_imports|Go 语言导入元素名称和类型列表|flattened|
|file.macho|file.macho.go_imports_names_entropy|从 Go 导入列表计算的 Shannon 熵|long|
|file.macho|file.macho.go_imports_names_var_entropy|Go 导入列表的 Shannon 熵方差|long|
|file.macho|file.macho.go_import_hash|Mach-O 文件中 Go 导入的哈希（排除标准库）|keyword|
|file.macho|file.macho.go_stripped|是否为已剥离符号或混淆的 Go 可执行文件|boolean|
|file.macho|file.macho.imports|Mach-O 文件导入元素名称和类型列表|flattened|
|file.macho|file.macho.imports_names_entropy|从导入元素名称和类型列表计算的 Shannon 熵|long|
|file.macho|file.macho.imports_names_var_entropy|导入元素名称和类型列表的 Shannon 熵方差|long|
|file.macho|file.macho.import_hash|Mach-O 文件导入的哈希（symhash 同义）|keyword|
|file.macho|file.macho.sections|Mach-O 文件的各 section 信息|nested|
|file.macho.sections|file.macho.sections.entropy|section 的 Shannon 熵|long|
|file.macho.sections|file.macho.sections.var_entropy|section 的 Shannon 熵方差|long|
|file.macho.sections|file.macho.sections.name|Mach-O section 名称|keyword|
|file.macho.sections|file.macho.sections.physical_size|Mach-O section 物理大小|long|
|file.macho.sections|file.macho.sections.virtual_size|Mach-O section 虚拟大小|long|
|file.macho|file.macho.symhash|Mach-O 文件导入的哈希，可用于指纹识别|keyword|
|file.pe|file.pe.go_imports|Go 语言导入元素名称和类型列表|flattened|
|file.pe|file.pe.go_imports_names_entropy|从 Go 导入列表计算的 Shannon 熵|long|
|file.pe|file.pe.go_imports_names_var_entropy|Go 导入列表的 Shannon 熵方差|long|
|file.pe|file.pe.go_import_hash|PE 文件中 Go 导入的哈希（排除标准库），可用于二进制指纹识别|keyword|
|file.pe|file.pe.go_stripped|是否为已剥离符号或混淆的 Go 可执行文件|boolean|
|file.pe|file.pe.imports|PE 文件导入元素名称和类型列表|flattened|
|file.pe|file.pe.imports_names_entropy|从导入元素名称和类型列表计算的 Shannon 熵|long|
|file.pe|file.pe.imports_names_var_entropy|导入元素名称和类型列表的 Shannon 熵方差|long|
|file.pe|file.pe.import_hash|PE 文件导入的哈希（imphash 同义）|keyword|
|file.pe|file.pe.sections|PE 文件的各 section 信息|nested|
|file.pe.sections|file.pe.sections.entropy|section 的 Shannon 熵|long|
|file.pe.sections|file.pe.sections.var_entropy|section 的 Shannon 熵方差|long|
|file.pe.sections|file.pe.sections.name|PE section 名称|keyword|
|file.pe.sections|file.pe.sections.physical_size|PE section 物理大小|long|
|file.pe.sections|file.pe.sections.virtual_size|PE section 虚拟大小|long|
|hash|hash.blake2b_256|文件的 BLAKE2b-256 哈希|keyword|
|hash|hash.blake2b_384|文件的 BLAKE2b-384 哈希|keyword|
|hash|hash.blake2b_512|文件的 BLAKE2b-512 哈希|keyword|
|hash|hash.md5|文件的 MD5 哈希|keyword|
|hash|hash.sha1|文件的 SHA1 哈希|keyword|
|hash|hash.sha224|文件的 SHA224 哈希|keyword|
|hash|hash.sha256|文件的 SHA256 哈希|keyword|
|hash|hash.sha384|文件的 SHA384 哈希|keyword|
|hash|hash.sha3_224|文件的 SHA3_224 哈希|keyword|
|hash|hash.sha3_256|文件的 SHA3_256 哈希|keyword|
|hash|hash.sha3_384|文件的 SHA3_384 哈希|keyword|
|hash|hash.sha3_512|文件的 SHA3_512 哈希|keyword|
|hash|hash.sha512|文件的 SHA512 哈希|keyword|
|hash|hash.sha512_224|文件的 SHA512/224 哈希|keyword|
|hash|hash.sha512_256|文件的 SHA512/256 哈希|keyword|
|hash|hash.xxh64|文件的 XXH64 哈希|keyword|
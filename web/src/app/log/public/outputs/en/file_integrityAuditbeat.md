### Auditbeat File Integrity Introduction

- &zwnj;**Basic Functions**&zwnj;
  - File change monitoring

  - File metadata collection

  - File content integrity verification

  - Recursive directory monitoring

  - Real-time event output

- &zwnj;**Key Features**&zwnj;
  - Security audit tool

  - Cross-platform support

  - Efficient and real-time

  - Highly configurable

  - Seamless integration with Elastic Stack

  - Typical use cases

### Auditbeat File Integrity Output Fields


|Group|Field Name|Description|Type|
|--------|------|------|--------|
|Built-in Fields|collect_type|Collection type|-|
|Built-in Fields|collector|Collector|-|
|Built-in Fields|instance_id|Instance ID|-|
|file.elf|file.elf.go_imports|List of Go language import element names and types|flattened|
|file.elf|file.elf.go_imports_names_entropy|Shannon entropy calculated from Go import list|long|
|file.elf|file.elf.go_imports_names_var_entropy|Shannon entropy variance of Go import list|long|
|file.elf|file.elf.go_import_hash|Hash of Go imports in ELF file (excluding standard library), can be used for binary fingerprinting|keyword|
|file.elf|file.elf.go_stripped|Whether it's a stripped or obfuscated Go executable|boolean|
|file.elf|file.elf.imports_names_entropy|Shannon entropy calculated from import element names and type list|long|
|file.elf|file.elf.imports_names_var_entropy|Shannon entropy variance of import element names and type list|long|
|file.elf|file.elf.import_hash|Hash of ELF file imports (similar to Windows PE imphash)|keyword|
|file.elf|file.elf.sections.var_entropy|Shannon entropy variance of sections in ELF file|long|
|file.macho|file.macho.go_imports|List of Go language import element names and types|flattened|
|file.macho|file.macho.go_imports_names_entropy|Shannon entropy calculated from Go import list|long|
|file.macho|file.macho.go_imports_names_var_entropy|Shannon entropy variance of Go import list|long|
|file.macho|file.macho.go_import_hash|Hash of Go imports in Mach-O file (excluding standard library)|keyword|
|file.macho|file.macho.go_stripped|Whether it's a stripped or obfuscated Go executable|boolean|
|file.macho|file.macho.imports|List of Mach-O file import element names and types|flattened|
|file.macho|file.macho.imports_names_entropy|Shannon entropy calculated from import element names and type list|long|
|file.macho|file.macho.imports_names_var_entropy|Shannon entropy variance of import element names and type list|long|
|file.macho|file.macho.import_hash|Hash of Mach-O file imports (synonym for symhash)|keyword|
|file.macho|file.macho.sections|Information about various sections in Mach-O file|nested|
|file.macho.sections|file.macho.sections.entropy|Shannon entropy of section|long|
|file.macho.sections|file.macho.sections.var_entropy|Shannon entropy variance of section|long|
|file.macho.sections|file.macho.sections.name|Mach-O section name|keyword|
|file.macho.sections|file.macho.sections.physical_size|Mach-O section physical size|long|
|file.macho.sections|file.macho.sections.virtual_size|Mach-O section virtual size|long|
|file.macho|file.macho.symhash|Hash of Mach-O file imports, can be used for fingerprinting|keyword|
|file.pe|file.pe.go_imports|List of Go language import element names and types|flattened|
|file.pe|file.pe.go_imports_names_entropy|Shannon entropy calculated from Go import list|long|
|file.pe|file.pe.go_imports_names_var_entropy|Shannon entropy variance of Go import list|long|
|file.pe|file.pe.go_import_hash|Hash of Go imports in PE file (excluding standard library), can be used for binary fingerprinting|keyword|
|file.pe|file.pe.go_stripped|Whether it's a stripped or obfuscated Go executable|boolean|
|file.pe|file.pe.imports|List of PE file import element names and types|flattened|
|file.pe|file.pe.imports_names_entropy|Shannon entropy calculated from import element names and type list|long|
|file.pe|file.pe.imports_names_var_entropy|Shannon entropy variance of import element names and type list|long|
|file.pe|file.pe.import_hash|Hash of PE file imports (synonym for imphash)|keyword|
|file.pe|file.pe.sections|Information about various sections in PE file|nested|
|file.pe.sections|file.pe.sections.entropy|Shannon entropy of section|long|
|file.pe.sections|file.pe.sections.var_entropy|Shannon entropy variance of section|long|
|file.pe.sections|file.pe.sections.name|PE section name|keyword|
|file.pe.sections|file.pe.sections.physical_size|PE section physical size|long|
|file.pe.sections|file.pe.sections.virtual_size|PE section virtual size|long|
|hash|hash.blake2b_256|BLAKE2b-256 hash of the file|keyword|
|hash|hash.blake2b_384|BLAKE2b-384 hash of the file|keyword|
|hash|hash.blake2b_512|BLAKE2b-512 hash of the file|keyword|
|hash|hash.md5|MD5 hash of the file|keyword|
|hash|hash.sha1|SHA1 hash of the file|keyword|
|hash|hash.sha224|SHA224 hash of the file|keyword|
|hash|hash.sha256|SHA256 hash of the file|keyword|
|hash|hash.sha384|SHA384 hash of the file|keyword|
|hash|hash.sha3_224|SHA3_224 hash of the file|keyword|
|hash|hash.sha3_256|SHA3_256 hash of the file|keyword|
|hash|hash.sha3_384|SHA3_384 hash of the file|keyword|
|hash|hash.sha3_512|SHA3_512 hash of the file|keyword|
|hash|hash.sha512|SHA512 hash of the file|keyword|
|hash|hash.sha512_224|SHA512/224 hash of the file|keyword|
|hash|hash.sha512_256|SHA512/256 hash of the file|keyword|
|hash|hash.xxh64|XXH64 hash of the file|keyword|
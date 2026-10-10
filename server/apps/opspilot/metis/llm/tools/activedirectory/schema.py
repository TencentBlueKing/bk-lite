"""Active Directory 虚拟关系表（对齐 CData AD JDBC 风格）。

表/列是给 LLM 用的 SQL 面，底层映射到 LDAP objectClass + attribute。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnDef:
    name: str
    ldap_attr: str
    data_type: str = "VARCHAR"
    remarks: str = ""


@dataclass(frozen=True)
class TableDef:
    name: str
    description: str
    object_filter: str
    columns: tuple[ColumnDef, ...]


def _cols(*items: tuple[str, str, str, str]) -> tuple[ColumnDef, ...]:
    return tuple(ColumnDef(name=n, ldap_attr=a, data_type=t, remarks=r) for n, a, t, r in items)


# CData Active Directory 驱动常见核心表 + 运维高频列。
AD_TABLES: dict[str, TableDef] = {
    "User": TableDef(
        name="User",
        description="Active Directory user accounts (person)",
        object_filter="(&(objectClass=user)(objectCategory=person))",
        columns=_cols(
            ("Id", "objectGUID", "VARCHAR", "Object GUID"),
            ("DN", "distinguishedName", "VARCHAR", "Distinguished Name"),
            ("CN", "cn", "VARCHAR", "Common Name"),
            ("SN", "sn", "VARCHAR", "Surname"),
            ("GivenName", "givenName", "VARCHAR", "Given name"),
            ("DisplayName", "displayName", "VARCHAR", "Display name"),
            ("Name", "name", "VARCHAR", "Name"),
            ("SAMAccountName", "sAMAccountName", "VARCHAR", "SAM account name"),
            ("UserPrincipalName", "userPrincipalName", "VARCHAR", "UPN"),
            ("Mail", "mail", "VARCHAR", "Email"),
            ("Title", "title", "VARCHAR", "Job title"),
            ("Department", "department", "VARCHAR", "Department"),
            ("Company", "company", "VARCHAR", "Company"),
            ("TelephoneNumber", "telephoneNumber", "VARCHAR", "Phone"),
            ("Mobile", "mobile", "VARCHAR", "Mobile"),
            ("StreetAddress", "streetAddress", "VARCHAR", "Street"),
            ("City", "l", "VARCHAR", "City"),
            ("State", "st", "VARCHAR", "State"),
            ("PostalCode", "postalCode", "VARCHAR", "Postal code"),
            ("Country", "co", "VARCHAR", "Country"),
            ("Manager", "manager", "VARCHAR", "Manager DN"),
            ("MemberOf", "memberOf", "VARCHAR", "Group membership DNs"),
            ("UserAccountControl", "userAccountControl", "INTEGER", "Account control flags"),
            ("WhenCreated", "whenCreated", "TIMESTAMP", "Created time"),
            ("WhenChanged", "whenChanged", "TIMESTAMP", "Changed time"),
            ("LastLogon", "lastLogonTimestamp", "TIMESTAMP", "Last logon"),
            ("Description", "description", "VARCHAR", "Description"),
            ("EmployeeID", "employeeID", "VARCHAR", "Employee ID"),
        ),
    ),
    "Group": TableDef(
        name="Group",
        description="Active Directory security and distribution groups",
        object_filter="(objectClass=group)",
        columns=_cols(
            ("Id", "objectGUID", "VARCHAR", "Object GUID"),
            ("DN", "distinguishedName", "VARCHAR", "Distinguished Name"),
            ("CN", "cn", "VARCHAR", "Common Name"),
            ("Name", "name", "VARCHAR", "Name"),
            ("SAMAccountName", "sAMAccountName", "VARCHAR", "SAM account name"),
            ("DisplayName", "displayName", "VARCHAR", "Display name"),
            ("Description", "description", "VARCHAR", "Description"),
            ("GroupType", "groupType", "INTEGER", "Group type flags"),
            ("Member", "member", "VARCHAR", "Member DNs"),
            ("MemberOf", "memberOf", "VARCHAR", "Parent group DNs"),
            ("ManagedBy", "managedBy", "VARCHAR", "Managed by DN"),
            ("WhenCreated", "whenCreated", "TIMESTAMP", "Created time"),
            ("WhenChanged", "whenChanged", "TIMESTAMP", "Changed time"),
        ),
    ),
    "Computer": TableDef(
        name="Computer",
        description="Active Directory computer accounts",
        object_filter="(objectClass=computer)",
        columns=_cols(
            ("Id", "objectGUID", "VARCHAR", "Object GUID"),
            ("DN", "distinguishedName", "VARCHAR", "Distinguished Name"),
            ("CN", "cn", "VARCHAR", "Common Name"),
            ("Name", "name", "VARCHAR", "Name"),
            ("SAMAccountName", "sAMAccountName", "VARCHAR", "SAM account name"),
            ("DisplayName", "displayName", "VARCHAR", "Display name"),
            ("DNSHostName", "dNSHostName", "VARCHAR", "DNS host name"),
            ("OperatingSystem", "operatingSystem", "VARCHAR", "OS"),
            ("OperatingSystemVersion", "operatingSystemVersion", "VARCHAR", "OS version"),
            ("OperatingSystemServicePack", "operatingSystemServicePack", "VARCHAR", "Service pack"),
            ("UserAccountControl", "userAccountControl", "INTEGER", "Account control flags"),
            ("MemberOf", "memberOf", "VARCHAR", "Group membership DNs"),
            ("WhenCreated", "whenCreated", "TIMESTAMP", "Created time"),
            ("WhenChanged", "whenChanged", "TIMESTAMP", "Changed time"),
            ("LastLogon", "lastLogonTimestamp", "TIMESTAMP", "Last logon"),
            ("Description", "description", "VARCHAR", "Description"),
        ),
    ),
    "Contact": TableDef(
        name="Contact",
        description="Active Directory contacts",
        object_filter="(objectClass=contact)",
        columns=_cols(
            ("Id", "objectGUID", "VARCHAR", "Object GUID"),
            ("DN", "distinguishedName", "VARCHAR", "Distinguished Name"),
            ("CN", "cn", "VARCHAR", "Common Name"),
            ("SN", "sn", "VARCHAR", "Surname"),
            ("GivenName", "givenName", "VARCHAR", "Given name"),
            ("DisplayName", "displayName", "VARCHAR", "Display name"),
            ("Mail", "mail", "VARCHAR", "Email"),
            ("TelephoneNumber", "telephoneNumber", "VARCHAR", "Phone"),
            ("Mobile", "mobile", "VARCHAR", "Mobile"),
            ("Company", "company", "VARCHAR", "Company"),
            ("Department", "department", "VARCHAR", "Department"),
            ("Title", "title", "VARCHAR", "Title"),
            ("WhenCreated", "whenCreated", "TIMESTAMP", "Created time"),
            ("WhenChanged", "whenChanged", "TIMESTAMP", "Changed time"),
            ("Description", "description", "VARCHAR", "Description"),
        ),
    ),
    "Organization": TableDef(
        name="Organization",
        description="Active Directory organizational units",
        object_filter="(objectClass=organizationalUnit)",
        columns=_cols(
            ("Id", "objectGUID", "VARCHAR", "Object GUID"),
            ("DN", "distinguishedName", "VARCHAR", "Distinguished Name"),
            ("OU", "ou", "VARCHAR", "OU name"),
            ("Name", "name", "VARCHAR", "Name"),
            ("DisplayName", "displayName", "VARCHAR", "Display name"),
            ("Description", "description", "VARCHAR", "Description"),
            ("ManagedBy", "managedBy", "VARCHAR", "Managed by DN"),
            ("WhenCreated", "whenCreated", "TIMESTAMP", "Created time"),
            ("WhenChanged", "whenChanged", "TIMESTAMP", "Changed time"),
            ("Street", "street", "VARCHAR", "Street"),
            ("City", "l", "VARCHAR", "City"),
            ("State", "st", "VARCHAR", "State"),
            ("PostalCode", "postalCode", "VARCHAR", "Postal code"),
            ("Country", "co", "VARCHAR", "Country"),
        ),
    ),
}


def list_table_names() -> list[str]:
    return list(AD_TABLES.keys())


def get_table(name: str) -> TableDef:
    key = (name or "").strip().strip('`"[]')
    # 大小写不敏感
    for table_name, table in AD_TABLES.items():
        if table_name.lower() == key.lower():
            return table
    raise KeyError(f"Unknown table: {name}")


def resolve_column(table: TableDef, column_name: str) -> ColumnDef:
    key = (column_name or "").strip().strip('`"[]')
    for col in table.columns:
        if col.name.lower() == key.lower():
            return col
    raise KeyError(f"Unknown column {column_name} on table {table.name}")

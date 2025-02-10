from neo4j import GraphDatabase
import json

# Настройки подключения к базе данных Neo4j
uri = "bolt://localhost:7687"  # Адрес вашего Neo4j сервера
user = "neo4j"  # Имя пользователя
password = "pin62gvin07"  # Пароль

# Путь к вашим JSON-файлам
json_files = {
    "users": "./users.json",
    "groups": "./groups.json",
    "roles": "./roles.json",
    "privileges": "./privileges.json",
    "permissions": "./permissions.json"
}

def load_json(file_path):
    """Загружает данные из JSON-файла."""
    with open(file_path, 'r') as file:
        return json.load(file)

def clean_id(dn):
    """Удаляет символ # и пробелы в начале и конце строки, но сохраняет пробелы внутри строки."""
    return dn.strip("# ").strip()

def remove_cn_prefix(dn):
    """Удаляет префикс 'cn=' из начала строки, если он присутствует."""
    if dn.startswith("cn="):
        return dn[3:]
    return dn

def create_node(tx, label, data):
    """Создает узел в Neo4j."""
    clean_node_id = clean_id(data['dn'].split(",")[0])  # Простой идентификатор
    query = f"""
    MERGE (n:{label} {{id: $id}})
    SET n += $data
    """
    tx.run(query, id=clean_node_id, data=data['attributes'])

def create_relationship(tx, start_label, start_id, end_label, end_id, relationship_type):
    """Создает связь между узлами в Neo4j."""
    start_id_clean = clean_id(start_id)
    end_id_clean = clean_id(remove_cn_prefix(end_id))
    
    query = f"""
    MATCH (start:{start_label} {{id: $start_id}})
    MATCH (end:{end_label} {{id: $end_id}})
    MERGE (start)-[:{relationship_type}]->(end)
    """
    tx.run(query, start_id=start_id_clean, end_id=end_id_clean)

def process_nodes(session, label, data):
    """Создание узлов для любой сущности."""
    for item in data:
        session.write_transaction(create_node, label, item)

def process_relationships(session, label, data):
    """Создание связей для любой сущности."""
    for item in data:
        clean_node_id = clean_id(item['dn'].split(",")[0])
        if 'memberOf' in item['attributes']:
            for related_dn in item['attributes']['memberOf']:
                related_dn_clean = clean_id(remove_cn_prefix(related_dn.split(",")[0]))
                if 'groups' in related_dn:
                    session.write_transaction(create_relationship, label, clean_node_id, 'Group', related_dn_clean, 'ЧЛЕН_ГРУППЫ')
                elif 'roles' in related_dn:
                    session.write_transaction(create_relationship, label, clean_node_id, 'Role', related_dn_clean, 'ИМЕЕТ_РОЛЬ')
                elif 'privileges' in related_dn:
                    session.write_transaction(create_relationship, 'Privilege', clean_node_id, 'Privilege', related_dn_clean, 'НАЗНАЧЕН')
        if label == 'Role' and 'memberOf' in item['attributes']:
            for related_dn in item['attributes']['memberOf']:
                related_dn_clean = clean_id(remove_cn_prefix(related_dn.split(",")[0]))
                if 'privileges' in related_dn:
                    session.write_transaction(create_relationship, 'Role', clean_node_id, 'Privilege', related_dn_clean, 'НАЗНАЧЕН')
        if label == 'Role' and 'member' in item['attributes']:
            for related_dn in item['attributes']['member']:
                related_dn_clean = clean_id(remove_cn_prefix(related_dn.split(",")[0]))
                if 'users' in related_dn:
                    session.write_transaction(create_relationship, 'Role', clean_node_id, 'User', related_dn_clean, 'НАЗНАЧЕН')
                elif 'groups' in related_dn:
                    session.write_transaction(create_relationship, 'Role', clean_node_id, 'Group', related_dn_clean, 'НАЗНАЧЕН')
        if label == 'Privilege' and 'memberOf' in item['attributes']:
            for related_dn in item['attributes']['memberOf']:
                related_dn_clean = clean_id(remove_cn_prefix(related_dn.split(",")[0]))
                if 'roles' in related_dn:
                    session.write_transaction(create_relationship, 'Privilege', clean_node_id, 'Role', related_dn_clean, 'НАЗНАЧЕН')
                if 'permissions' in related_dn:
                    session.write_transaction(create_relationship, 'Privilege', clean_node_id, 'Permission', related_dn_clean, 'ИМЕЕТ_РАЗРЕШЕНИЕ')

def link_dangerous_permissions(session):
    dangerous_permissions_1 = {
        "System: Modify Group Membership": "ИЗМЕНЕНИЕ_ЧЛЕНСТВА_В_ГРУППЕ",
        "System: Modify Groups": "ИЗМЕНЕНИЕ_ГРУППЫ",
        "System: Change User password": "СМЕНА_ПАРОЛЯ_ПОЛЬЗОВАТЕЛЯ",
        "System: Change Admin User password": "СМЕНА_ПАРОЛЯ_АДМИНИСТРАТОРА",
        "System: Manage User Certificates": "УПРАВЛЕНИЕ_СЕРТИФИКАТАМИ_ПОЛЬЗОВАТЕЛЯ",
        "System: Modify Users": "ИЗМЕНЕНИЕ_ПОЛЬЗОВАТЕЛЯ"
    }
    
    dangerous_permissions_2 = {
        "System: Modify Privilege Membership": "ИЗМЕНЕНИЕ_ЧЛЕНСТВА_В_ПРИВИЛЕГИИ",
        "System: Add Privileges": "ДОБАВЛЕНИЕ_ПРИВИЛЕГИЙ",
        "System: Modify Privileges": "ИЗМЕНЕНИЕ_ПРИВИЛЕГИЙ",
        "System: Add Roles": "ДОБАВЛЕНИЕ_РОЛЕЙ",
        "System: Modify Role Membership": "ИЗМЕНЕНИЕ_ЧЛЕНСТВА_В_РОЛИ",
        "System: Modify Roles": "ИЗМЕНЕНИЕ_РОЛЕЙ"
    }
    for perm, rel_name in dangerous_permissions_1.items():
        query = f"""
        MATCH (p:Permission {{id: $perm}})
        MATCH (target:User)
        MERGE (p)-[:{rel_name}]->(target)
        """
        session.run(query, perm=perm)
    
    for perm, rel_name in dangerous_permissions_2.items():
        query = f"""
        MATCH (p:Permission {{id: $perm}})
        MATCH (target)
        WHERE target:User OR target:Group
        MERGE (p)-[:{rel_name}]->(target)
        """
        session.run(query, perm=perm)


# Теперь для пермишенов "System: Modify Group Membership" и "System: Modify Groups" добавим связки
    dangerous_permissions_group = [
        "System: Modify Group Membership",
        "System: Modify Groups"
    ]
    
    for perm in dangerous_permissions_group:
        # Принт для отладки
        print(f"Добавляем связь для пермишена {perm} (ID: {perm}): с группами...")
        
        # Вывод ID пермишена
        query_id = "MATCH (p:Permission {id: $perm}) RETURN id(p) AS permission_id"
        result = session.run(query_id, perm=perm)
        for record in result:
            print(f"ID пермишена: {record['permission_id']}")
        
        # Связь с каждой группой
        query = """
        MATCH (p:Permission {id: $perm})
        MATCH (group:Group)
        MERGE (p)-[:МОЖЕТ_ИЗМЕНИТЬ]->(group)
        """
        session.run(query, perm=perm)

        # Добавление связей для продолжения
        query_continue = """
        MATCH (p:Permission {id: $perm})
        MATCH (group:Group)-[:ЧЛЕН_ГРУППЫ]->(user:User)
        MERGE (p)-[:МОЖЕТ_ИЗМЕНИТЬ]->(user)
        """
        session.run(query_continue, perm=perm)

def main():
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    with driver.session() as session:
        users_data = load_json(json_files['users'])
        groups_data = load_json(json_files['groups'])
        roles_data = load_json(json_files['roles'])
        privileges_data = load_json(json_files['privileges'])
        permissions_data = load_json(json_files['permissions'])

        # Создание узлов
        process_nodes(session, 'User', users_data)
        process_nodes(session, 'Group', groups_data)
        process_nodes(session, 'Role', roles_data)
        process_nodes(session, 'Privilege', privileges_data)
        process_nodes(session, 'Permission', permissions_data)

        # Создание связей между узлами
        process_relationships(session, 'User', users_data)
        process_relationships(session, 'Group', groups_data)
        process_relationships(session, 'Role', roles_data)
        process_relationships(session, 'Privilege', privileges_data)
        process_relationships(session, 'Permission', permissions_data)

        # Добавление опасных прав
        link_dangerous_permissions(session)

    driver.close()

if __name__ == "__main__":
    main()

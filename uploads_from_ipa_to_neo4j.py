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
    print(f"Created node {label} with ID {clean_node_id}")

def create_relationship(tx, start_label, start_id, end_label, end_id, relationship_type):
    """Создает связь между узлами в Neo4j."""
    start_id_clean = clean_id(start_id)
    end_id_clean = clean_id(remove_cn_prefix(end_id))
    
    print(f"Attempting to create relationship '{relationship_type}' from {start_label} '{start_id_clean}' to {end_label} '{end_id_clean}'")

    query = f"""
    MATCH (start:{start_label} {{id: $start_id}})
    MATCH (end:{end_label} {{id: $end_id}})
    MERGE (start)-[:`{relationship_type}`]->(end)
    """
    result = tx.run(query, start_id=start_id_clean, end_id=end_id_clean)
    if result.consume().counters.relationships_created:
        print(f"Created relationship '{relationship_type}' from {start_label} '{start_id_clean}' to {end_label} '{end_id_clean}'")
    else:
        print(f"Failed to create relationship '{relationship_type}'.")

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

def link_users_to_groups(session, users_data, groups_data):
    """Связывает пользователей с группами по имени группы."""
    user_group_map = {clean_id(user['dn'].split(",")[0]): user['attributes'].get('memberOf', []) for user in users_data}
    for group in groups_data:
        group_id = clean_id(group['dn'].split(",")[0])
        for user_id, memberships in user_group_map.items():
            if group_id in memberships:
                session.write_transaction(create_relationship, 'User', user_id, 'Group', group_id, 'ЧЛЕН_ГРУППЫ')

def main():
    # Подключение к базе данных Neo4j
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    with driver.session() as session:
        # Загрузка данных из JSON-файлов
        users_data = load_json(json_files['users'])
        groups_data = load_json(json_files['groups'])
        roles_data = load_json(json_files['roles'])
        privileges_data = load_json(json_files['privileges'])
        permissions_data = load_json(json_files['permissions'])

        # Сначала создаем все узлы
        process_nodes(session, 'User', users_data)
        process_nodes(session, 'Group', groups_data)
        process_nodes(session, 'Role', roles_data)
        process_nodes(session, 'Privilege', privileges_data)
        process_nodes(session, 'Permission', permissions_data)

        # Затем создаем все связи между узлами
        process_relationships(session, 'User', users_data)
        process_relationships(session, 'Group', groups_data)
        process_relationships(session, 'Role', roles_data)
        process_relationships(session, 'Privilege', privileges_data)
        process_relationships(session, 'Permission', permissions_data)

        # Создаем связи между пользователями и их группами
        link_users_to_groups(session, users_data, groups_data)

    driver.close()

if __name__ == "__main__":
    main()

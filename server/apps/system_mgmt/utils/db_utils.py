from django.db import connection

from apps.core.logger import logger


class SQLExecute(object):
    @staticmethod
    def execute_sql(sql, args, db_name="keycloak"):
        db_config = connection.get_connection_params()
        db_config["dbname"] = db_name
        sql_connection = connection.get_new_connection(db_config)
        cursor = sql_connection.cursor()
        try:
            if isinstance(args, str):
                args = [args]
            elif isinstance(args, int):
                args = [str(args)]
            cursor.execute(sql, args)
            result = cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            return_data = [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.exception(e)
            return_data = []
        cursor.close()
        sql_connection.close()
        return return_data

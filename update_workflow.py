import json

def main():
    try:
        with open('c:/Users/alex.biudes/Desktop/Documentação/MCP/Equipe clickup/My workflow.json', 'r', encoding='utf-8') as f:
            wf = json.load(f)

        nodes_map = {n['name']: n for n in wf['nodes']}

        code_node = {
            'parameters': {
                'jsCode': 'for (const item of $input.all()) {\n  const match = item.json.name ? item.json.name.match(/UAID[:\\-\\s]*([a-zA-Z0-9\\-]+)/i) : null;\n  if (match && match[1]) {\n    item.json.is_valid_uaid = true;\n    item.json.extracted_uaid = match[1];\n  } else {\n    item.json.is_valid_uaid = false;\n    item.json.extracted_uaid = null;\n  }\n}\nreturn $input.all();'
            },
            'type': 'n8n-nodes-base.code',
            'typeVersion': 2,
            'position': [0, -320],
            'id': 'code-extract-uaid',
            'name': 'Extract UAID'
        }

        if_uaid_node = {
            'parameters': {
                'conditions': {
                    'options': {
                        'caseSensitive': True,
                        'leftValue': '',
                        'typeValidation': 'loose',
                        'version': 3
                    },
                    'conditions': [
                        {
                            'id': 'cond-uaid-1',
                            'leftValue': '={{ $json.extracted_uaid }}',
                            'rightValue': '',
                            'operator': {
                                'type': 'string',
                                'operation': 'isNotEmpty',
                                'singleValue': True
                            }
                        }
                    ],
                    'combinator': 'and'
                },
                'looseTypeValidation': True,
                'options': {}
            },
            'type': 'n8n-nodes-base.if',
            'typeVersion': 2.3,
            'position': [200, -320],
            'id': 'if-check-uaid',
            'name': 'If UAID Exists'
        }

        comment_no_uaid = {
            'parameters': {
                'operation': 'create',
                'taskId': '={{ $json.id }}',
                'commentText': 'UAID não encontrado no título da tarefa. Por favor, verifique e corrija o título.',
                'assignees': []
            },
            'type': 'n8n-nodes-base.clickUp',
            'typeVersion': 1,
            'position': [400, -150],
            'id': 'comment-no-uaid',
            'name': 'Comment No UAID',
            'credentials': {
                'clickUpApi': {
                    'id': 'M1llSyeGDORkhGjQ',
                    'name': 'ClickUp account'
                }
            }
        }

        comment_not_bq = {
            'parameters': {
                'operation': 'create',
                'taskId': '={{ $json.id }}',
                'commentText': 'O UAID \'{{ $json.extracted_uaid }}\' não foi encontrado na base do BigQuery.',
                'assignees': []
            },
            'type': 'n8n-nodes-base.clickUp',
            'typeVersion': 1,
            'position': [688, -50],
            'id': 'comment-not-bq',
            'name': 'Comment Not in BQ',
            'credentials': {
                'clickUpApi': {
                    'id': 'M1llSyeGDORkhGjQ',
                    'name': 'ClickUp account'
                }
            }
        }

        nodes_map['Execute a SQL query']['parameters']['sqlQuery'] = "SELECT \n  (SELECT UAID FROM `bi-performance.BI_PROD.BALANCETE_ERP` WHERE UAID = '{{ $json.extracted_uaid }}' LIMIT 1) as uaid_encontrado,\n  '{{ $json.id }}' as task_id"
        nodes_map['Execute a SQL query']['position'] = [400, -480]

        nodes_map['If']['parameters']['conditions']['conditions'][0] = {
            'id': 'cond-bq-1',
            'leftValue': '={{ $json.uaid_encontrado }}',
            'rightValue': '',
            'operator': {
                'type': 'string',
                'operation': 'isNotEmpty',
                'singleValue': True
            }
        }
        nodes_map['If']['position'] = [600, -352]

        wf['nodes'].extend([code_node, if_uaid_node, comment_no_uaid, comment_not_bq])

        wf['connections'] = {
            'Schedule Trigger': {
                'main': [ [ {'node': 'Get many tasks', 'type': 'main', 'index': 0} ] ]
            },
            'Get many tasks': {
                'main': [ [ {'node': 'If1', 'type': 'main', 'index': 0} ] ]
            },
            'If1': {
                'main': [ [ {'node': 'Extract UAID', 'type': 'main', 'index': 0} ] ]
            },
            'Extract UAID': {
                'main': [ [ {'node': 'If UAID Exists', 'type': 'main', 'index': 0} ] ]
            },
            'If UAID Exists': {
                'main': [
                    [ {'node': 'Execute a SQL query', 'type': 'main', 'index': 0} ], 
                    [ {'node': 'Comment No UAID', 'type': 'main', 'index': 0} ]      
                ]
            },
            'Comment No UAID': {
                'main': [ [ {'node': 'Update a task1', 'type': 'main', 'index': 0} ] ]
            },
            'Execute a SQL query': {
                'main': [ [ {'node': 'If', 'type': 'main', 'index': 0} ] ]
            },
            'If': {
                'main': [
                    [ {'node': 'Update a task', 'type': 'main', 'index': 0} ],       
                    [ {'node': 'Comment Not in BQ', 'type': 'main', 'index': 0} ]    
                ]
            },
            'Comment Not in BQ': {
                'main': [ [ {'node': 'Update a task1', 'type': 'main', 'index': 0} ] ] 
            }
        }

        nodes_map['Update a task']['position'] = [900, -544]
        nodes_map['Update a task1']['position'] = [900, -240]

        with open('c:/Users/alex.biudes/Desktop/Documentação/MCP/Equipe clickup/My workflow.json', 'w', encoding='utf-8') as f:
            json.dump(wf, f, indent=2, ensure_ascii=False)

        with open('c:/Users/alex.biudes/Desktop/Documentação/MCP/Equipe clickup/My workflow.n8n', 'w', encoding='utf-8') as f:
            json.dump(wf, f, indent=2, ensure_ascii=False)

        print('Updated successfully')
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()

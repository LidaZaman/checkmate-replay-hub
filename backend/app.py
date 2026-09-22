import json
import os
import uuid
import boto3

dynamodb = boto3.resource('dynamodb')
ses = boto3.client('ses')

TABLE_NAME = os.environ.get('TABLE_NAME')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'test@example.com')

table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

def submit_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        email = body.get('email')
        moves = body.get('moves')

        if not email or not moves:
            return {
                'statusCode': 400,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Email und Zuege erforderlich'})
            }

        submission_id = str(uuid.uuid4())
        token = str(uuid.uuid4())

        table.put_item(
            Item={
                'id': submission_id,
                'email': email,
                'moves': moves,
                'status': 'AWAITING_CONFIRMATION',
                'confirmation_token': token
            }
        )

        # استخراج خودکار نشانی دامنه API از ریکوئست ورودی
        domain = event.get('requestContext', {}).get('domainName', '')
        stage = event.get('requestContext', {}).get('stage', '')
        base_url = f"https://{domain}" if not stage or stage == '$default' else f"https://{domain}/{stage}"
        confirm_url = f"{base_url}/confirm?id={submission_id}&token={token}"

        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': 'Checkmate Replay Hub - Bestaetigung'},
                'Body': {
                    'Text': {
                        'Data': f"Bitte bestaetigen Sie Ihre Einreichung:\n{confirm_url}"
                    }
                }
            }
        )

        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'submissionId': submission_id,
                'status': 'AWAITING_CONFIRMATION'
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }

def confirm_handler(event, context):
    params = event.get('queryStringParameters') or {}
    submission_id = params.get('id')
    token = params.get('token')

    if not submission_id or not token:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'text/html; charset=utf-8'},
            'body': '<h2>Ungueltiger Link</h2><p>Parameter fehlen.</p>'
        }

    try:
        response = table.get_item(Key={'id': submission_id})
        item = response.get('Item')

        if not item:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'text/html; charset=utf-8'},
                'body': '<h2>Einreichung nicht gefunden</h2>'
            }

        if item.get('status') == 'PROCESSING':
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'text/html; charset=utf-8'},
                'body': '<h2>Bereits bestaetigt</h2><p>Status ist bereits PROCESSING.</p>'
            }

        if item.get('confirmation_token') != token:
            return {
                'statusCode': 403,
                'headers': {'Content-Type': 'text/html; charset=utf-8'},
                'body': '<h2>Ungueltiger Token</h2><p>Link abgelaufen oder unguetlig.</p>'
            }

        table.update_item(
            Key={'id': submission_id},
            UpdateExpression="SET #st = :p REMOVE confirmation_token",
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues={':p': 'PROCESSING'}
        )

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'text/html; charset=utf-8'},
            'body': '<h2>Erfolgreich bestaetigt!</h2><p>Status: PROCESSING</p>'
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'text/html; charset=utf-8'},
            'body': f'<h2>Fehler</h2><p>{str(e)}</p>'
        }
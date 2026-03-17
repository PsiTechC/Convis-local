import {
	IHookFunctions,
	IWebhookFunctions,
	INodeType,
	INodeTypeDescription,
	IWebhookResponseData,
} from 'n8n-workflow';

export class ConvisTrigger implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'Convis Trigger',
		name: 'convisTrigger',
		icon: 'file:convis.svg',
		group: ['trigger'],
		version: 1,
		subtitle: '={{$parameter["event"]}}',
		description: 'Trigger workflows from Convis call events',
		defaults: {
			name: 'Convis Trigger',
		},
		inputs: [],
		outputs: ['main'],
		credentials: [],
		webhooks: [
			{
				name: 'default',
				httpMethod: 'POST',
				responseMode: 'onReceived',
				path: 'convis',
			},
		],
		properties: [
			{
				displayName: 'Event',
				name: 'event',
				type: 'options',
				options: [
					{
						name: 'Call Completed',
						value: 'call_completed',
						description: 'Triggered when a call ends successfully',
					},
					{
						name: 'Call Failed',
						value: 'call_failed',
						description: 'Triggered when a call fails',
					},
					{
						name: 'Call No Answer',
						value: 'call_no_answer',
						description: 'Triggered when no one answers the call',
					},
					{
						name: 'Campaign Completed',
						value: 'campaign_completed',
						description: 'Triggered when a campaign finishes',
					},
					{
						name: 'All Events',
						value: 'all',
						description: 'Receive all Convis events',
					},
				],
				default: 'call_completed',
				description: 'The event to listen for',
			},
			{
				displayName: 'Options',
				name: 'options',
				type: 'collection',
				placeholder: 'Add Option',
				default: {},
				options: [
					{
						displayName: 'Filter by Sentiment',
						name: 'sentimentFilter',
						type: 'options',
						options: [
							{ name: 'All', value: 'all' },
							{ name: 'Positive Only', value: 'positive' },
							{ name: 'Negative Only', value: 'negative' },
							{ name: 'Neutral Only', value: 'neutral' },
						],
						default: 'all',
						description: 'Only trigger for calls with specific sentiment',
					},
					{
						displayName: 'Minimum Call Duration (seconds)',
						name: 'minDuration',
						type: 'number',
						default: 0,
						description: 'Only trigger for calls longer than this duration',
					},
				],
			},
		],
	};

	async webhook(this: IWebhookFunctions): Promise<IWebhookResponseData> {
		const req = this.getRequestObject();
		const body = this.getBodyData();

		const event = this.getNodeParameter('event') as string;
		const options = this.getNodeParameter('options', {}) as {
			sentimentFilter?: string;
			minDuration?: number;
		};

		// Filter by event type
		if (event !== 'all' && body.event !== event) {
			return {
				noWebhookResponse: true,
			};
		}

		// Filter by sentiment
		if (options.sentimentFilter && options.sentimentFilter !== 'all') {
			const callSentiment = (body as any).call?.sentiment;
			if (callSentiment && callSentiment !== options.sentimentFilter) {
				return {
					noWebhookResponse: true,
				};
			}
		}

		// Filter by minimum duration
		if (options.minDuration && options.minDuration > 0) {
			const callDuration = (body as any).call?.duration || 0;
			if (callDuration < options.minDuration) {
				return {
					noWebhookResponse: true,
				};
			}
		}

		// Return the data for the workflow
		return {
			workflowData: [
				this.helpers.returnJsonArray(body as any),
			],
		};
	}
}

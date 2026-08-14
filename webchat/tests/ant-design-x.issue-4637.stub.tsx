import React from 'react';

export const Bubble = ({ content }: { content?: React.ReactNode }) => <div>{content}</div>;

export const Sender = (props: Record<string, unknown>) => <div {...props} />;

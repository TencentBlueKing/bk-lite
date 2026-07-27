import React, { memo } from 'react';
import { Image, Button } from 'antd-mobile';

// 卡片内容类型定义
export type CardContentItem =
    | { type: 'text'; content: string }
    | { type: 'paragraph'; content: string }
    | { type: 'list'; items: string[] }
    | { type: 'image'; src: string; alt?: string }
    | { type: 'images'; images: Array<{ src: string; alt?: string }> }
    | { type: 'divider' }
    | { type: 'button'; text: string; message: string }; // 添加 message 属性

export interface InformationCardProps {
    content: CardContentItem[];
    onButtonClick?: (message: string) => void; // 按钮点击回调
}

const InformationCardComponent: React.FC<InformationCardProps> = ({ content, onButtonClick }) => {
    const [isSubmitting, setIsSubmitting] = React.useState(false);
    const renderContentItem = (item: CardContentItem, index: number) => {
        switch (item.type) {
            case 'text':
                return (
                    <div key={index} className="text-sm text-[var(--color-text-1)] mb-2">
                        {item.content}
                    </div>
                );

            case 'paragraph':
                return (
                    <p key={index} className="text-sm text-[var(--color-text-2)] leading-relaxed mb-3">
                        {item.content}
                    </p>
                );

            case 'list':
                return (
                    <ul key={index} className="mb-3 pl-4">
                        {item.items.map((listItem, idx) => (
                            <li key={idx} className="text-sm text-[var(--color-text-2)] mb-1.5 list-disc">
                                {listItem}
                            </li>
                        ))}
                    </ul>
                );

            case 'image':
                return (
                    <div key={index} className="mb-3">
                        <Image
                            src={item.src}
                            alt={item.alt || '图片'}
                            fit="contain"
                            style={{ maxWidth: '100%', borderRadius: '8px' }}
                        />
                    </div>
                );

            case 'images':
                return (
                    <div key={index} className="grid grid-cols-2 gap-2 mb-3">
                        {item.images.map((img, idx) => (
                            <Image
                                key={idx}
                                src={img.src}
                                alt={img.alt || `图片${idx + 1}`}
                                fit="cover"
                                style={{ width: '100%', borderRadius: '8px', aspectRatio: '1' }}
                            />
                        ))}
                    </div>
                );

            case 'divider':
                return (
                    <div key={index} className="border-b border-[var(--color-border)] my-3"></div>
                );

            case 'button':
                return (
                    <div key={index} className="mt-3">
                        <Button
                            color={isSubmitting ? "default" : "primary"}
                            block
                            disabled={isSubmitting}
                            onClick={() => {
                                setIsSubmitting(true);
                                if (onButtonClick) {
                                    onButtonClick(item.message);
                                }
                            }}
                            className="rounded-lg"
                            style={
                                {
                                    '--adm-font-size-9': '15px'
                                } as React.CSSProperties}
                        >
                            {isSubmitting ? '已提交' : item.text}
                        </Button>
                    </div>
                );

            default:
                return null;
        }
    };

    return (
        <div className="w-full">
            <div className="bg-[var(--color-fill-2)] rounded-2xl p-4">
                {content.map((item, index) => renderContentItem(item, index))}
            </div>
        </div>
    );
};

// 使用 memo 优化性能
export const InformationCard = memo(InformationCardComponent);

import React from 'react';
import { cn } from '../../lib/utils';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'raised' | 'elevated' | 'ghost';
}

export const Card: React.FC<CardProps> = ({
  className,
  variant = 'default',
  children,
  ...props
}) => {
  const variants = {
    default: 'bg-surface border-border',
    raised: 'bg-surface-raised border-border',
    elevated: 'bg-surface-elevated border-border-hover shadow-lg',
    ghost: 'bg-transparent border-transparent',
  };

  return (
    <div
      className={cn(
        'rounded-lg border p-4 transition-colors',
        variants[variant],
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardHeader: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  className,
  ...props
}) => (
  <div className={cn('flex items-center justify-between pb-3 mb-3 border-b border-border-subtle', className)} {...props} />
);

export const CardTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({
  className,
  ...props
}) => (
  <h3 className={cn('text-sm font-semibold text-text-primary tracking-wide uppercase font-mono', className)} {...props} />
);

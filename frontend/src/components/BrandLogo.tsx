import React from 'react';
import { Link } from 'react-router-dom';

export interface BrandLogoProps {
  showSlogan?: boolean;
  theme?: 'light' | 'dark'; // 'light' when rendered on dark backgrounds; 'dark' when rendered on light surfaces
  size?: 'sm' | 'md' | 'lg';
  to?: string;
  className?: string;
}

export const BrandLogo: React.FC<BrandLogoProps> = ({
  showSlogan = true,
  theme = 'light',
  size = 'md',
  to = '/',
  className = '',
}) => {
  const isSm = size === 'sm';
  const isLg = size === 'lg';

  const imgWidth = isSm ? 120 : isLg ? 168 : 144;
  const imgHeight = isSm ? 24 : isLg ? 34 : 29;

  const content = (
    <div className={`edu-brand-block ${className}`}>
      <div className="edu-brand-badge">
        <img
          src="/images/logo.jpg"
          alt="EduManage — A smarter way to manage your school"
          style={{
            width: imgWidth,
            height: imgHeight,
            objectFit: 'cover',
            objectPosition: 'center',
            display: 'block',
          }}
          loading="eager"
        />
      </div>
      {showSlogan && (
        <span
          className={`edu-brand-slogan ${theme === 'dark' ? 'dark' : ''}`}
          style={{
            fontSize: isSm ? '11px' : 'var(--font-size-xs)',
          }}
        >
          A smarter way to manage your school
        </span>
      )}
    </div>
  );

  if (to) {
    return (
      <Link to={to} style={{ textDecoration: 'none' }} aria-label="EduManage Home">
        {content}
      </Link>
    );
  }

  return content;
};

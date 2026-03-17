'use client';

import { useMemo, useState, Suspense, ReactNode } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

export interface NavigationItem {
  name: string;
  icon: ReactNode;
  href?: string;
  subItems?: SubNavigationItem[];
}

export interface SubNavigationItem {
  name: string;
  icon: ReactNode;
  href: string;
  logo?: ReactNode;
}

export const NAV_ITEMS: NavigationItem[] = [
  {
    name: 'Dashboard',
    href: '/dashboard',
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
    ),
  },
  {
    name: 'AI Agent',
    href: '/ai-agent',
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
    ),
  },
  {
    name: 'Voice Lab',
    href: '/voice-lab',
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
    ),
  },
  {
    name: 'Phone Numbers',
    href: '/phone-numbers',
    icon: (
      <>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M8 2h8a2 2 0 012 2v16a2 2 0 01-2 2H8a2 2 0 01-2-2V4a2 2 0 012-2z"
        />
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M10 6h4m-4 4h4m-4 4h2"
        />
      </>
    ),
  },
  {
    name: 'Call logs',
    href: '/phone-numbers?tab=calls',
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
    ),
  },
  {
    name: 'Campaigns',
    href: '/campaigns',
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
    ),
  },
  {
    name: 'Integrations',
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 14v6m-3-3h6M6 10h2a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v2a2 2 0 002 2zm10 0h2a2 2 0 002-2V6a2 2 0 00-2-2h-2a2 2 0 00-2 2v2a2 2 0 002 2zM6 20h2a2 2 0 002-2v-2a2 2 0 00-2-2H6a2 2 0 00-2 2v2a2 2 0 002 2z" />
    ),
    subItems: [
      {
        name: 'Overview',
        href: '/integrations',
        icon: (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        ),
        logo: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        ),
      },
      {
        name: 'Calendar',
        href: '/connect-calendar',
        icon: (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        ),
        logo: (
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zM9 14H7v-2h2v2zm4 0h-2v-2h2v2zm4 0h-2v-2h2v2zm-8 4H7v-2h2v2zm4 0h-2v-2h2v2zm4 0h-2v-2h2v2z"/>
          </svg>
        ),
      },
      {
        name: 'Jira',
        href: '/integrations/jira',
        icon: (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        ),
        logo: (
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005zm5.723-5.756H5.736a5.215 5.215 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.757a1.001 1.001 0 0 0-1.001-1.001zM23.013 0H11.455a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24 12.483V1.005A1.001 1.001 0 0 0 23.013 0z" fill="#2684FF"/>
          </svg>
        ),
      },
      {
        name: 'HubSpot',
        href: '/integrations/hubspot',
        icon: (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
        ),
        logo: (
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M18.164 7.93V5.084a2.198 2.198 0 0 0 1.267-1.978v-.087A2.187 2.187 0 0 0 17.244.832h-.087a2.187 2.187 0 0 0-2.187 2.187v.087a2.198 2.198 0 0 0 1.267 1.978v2.846a3.658 3.658 0 0 0-2.035.832l-3.852-2.814a2.35 2.35 0 1 0-1.123.953l3.81 2.78a3.724 3.724 0 0 0-.887 2.418c0 .866.297 1.663.792 2.293L8.333 18.1a2.677 2.677 0 0 0-1.516-.47c-1.48 0-2.678 1.198-2.678 2.677S5.337 23.006 6.817 23.006s2.678-1.198 2.678-2.678c0-.467-.12-.905-.33-1.287l4.596-3.708a3.698 3.698 0 0 0 6.553-2.335 3.698 3.698 0 0 0-3.7-3.7 3.698 3.698 0 0 0-1.45.297z" fill="#FF7A59"/>
          </svg>
        ),
      },
      {
        name: 'Email',
        href: '/integrations/email',
        icon: (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        ),
        logo: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        ),
      },
      {
        name: 'WhatsApp',
        href: '/whatsapp',
        icon: (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        ),
        logo: (
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.890-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z" fill="#25D366"/>
          </svg>
        ),
      },
      {
        name: 'Workflows',
        href: '/workflows',
        icon: (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        ),
        logo: (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        ),
      },
    ],
  },
  {
    name: 'Settings',
    href: '/settings',
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    ),
  },
];

interface NavigationProps {
  isSidebarCollapsed: boolean;
  setIsSidebarCollapsed: (value: boolean) => void;
  isDarkMode: boolean;
}

function SidebarNavigationContent({ isSidebarCollapsed, setIsSidebarCollapsed, isDarkMode }: NavigationProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab = searchParams?.get('tab');
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  const activeItem = useMemo(() => {
    if (!pathname) {
      return '';
    }

    if (pathname.startsWith('/phone-numbers')) {
      return activeTab === 'calls' ? 'Call logs' : 'Phone Numbers';
    }

    if (pathname.startsWith('/campaigns')) {
      return 'Campaigns';
    }

    const matched = NAV_ITEMS.find((nav) => {
      if (nav.href && nav.href.includes('?')) {
        return pathname === nav.href.split('?')[0];
      }
      return nav.href && pathname === nav.href;
    });

    return matched?.name ?? '';
  }, [pathname, activeTab]);

  return (
    <aside
      onMouseEnter={() => setIsSidebarCollapsed(false)}
      onMouseLeave={() => setIsSidebarCollapsed(true)}
      className={`fixed left-0 top-0 h-full ${isDarkMode ? 'bg-gray-800' : 'bg-white'} border-r ${isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'} transition-all duration-300 z-40 ${isSidebarCollapsed ? 'w-20' : 'w-64'} hidden lg:block`}
    >
      <div className="h-16 flex items-center justify-center border-b border-neutral-mid/10">
        <div className={`flex items-center gap-2 transition-all duration-300 ${isSidebarCollapsed ? 'scale-90' : 'scale-100'}`}>
          <div className="w-8 h-8 bg-gradient-to-br from-primary to-primary/80 rounded-lg"></div>
          {!isSidebarCollapsed && (
            <span className={`text-lg font-bold ${isDarkMode ? 'text-white' : 'text-dark'}`}>Convis AI</span>
          )}
        </div>
      </div>

      <nav className="p-4 space-y-2">
        {NAV_ITEMS.map((item) => {
          const isActive = activeItem === item.name;
          const hasSubItems = item.subItems && item.subItems.length > 0;
          const isDropdownOpen = openDropdown === item.name;

          return (
            <div key={item.name}>
              <button
                onClick={() => {
                  if (hasSubItems) {
                    setOpenDropdown(isDropdownOpen ? null : item.name);
                  } else if (item.href) {
                    router.push(item.href);
                  }
                }}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 ${
                  isActive
                    ? `${isDarkMode ? 'bg-gray-700 text-white' : 'bg-primary/10 text-primary'}`
                    : `${isDarkMode ? 'text-gray-400 hover:bg-gray-700 hover:text-white' : 'text-dark/60 hover:bg-neutral-light hover:text-dark'}`
                }`}
              >
                <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  {item.icon}
                </svg>
                {!isSidebarCollapsed && (
                  <>
                    <span className="font-medium flex-1 text-left">{item.name}</span>
                    {hasSubItems && (
                      <svg
                        className={`w-4 h-4 transition-transform duration-200 ${isDropdownOpen ? 'rotate-180' : ''}`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    )}
                  </>
                )}
              </button>

              {/* Dropdown sub-items */}
              {hasSubItems && isDropdownOpen && !isSidebarCollapsed && (
                <div className="ml-4 mt-2 space-y-1">
                  {item.subItems?.map((subItem) => {
                    const isSubItemActive = pathname === subItem.href;
                    return (
                      <button
                        key={subItem.name}
                        onClick={() => router.push(subItem.href)}
                        className={`w-full flex items-center gap-3 px-4 py-2 rounded-lg transition-all duration-200 ${
                          isSubItemActive
                            ? `${isDarkMode ? 'bg-gray-600 text-white' : 'bg-primary/5 text-primary border-l-2 border-primary'}`
                            : `${isDarkMode ? 'text-gray-400 hover:bg-gray-600 hover:text-white' : 'text-dark/50 hover:bg-neutral-light/50 hover:text-dark'}`
                        }`}
                      >
                        <div className={`flex-shrink-0 ${isSubItemActive ? 'text-primary' : isDarkMode ? 'text-gray-500' : 'text-dark/40'}`}>
                          {subItem.logo || (
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              {subItem.icon}
                            </svg>
                          )}
                        </div>
                        <span className="font-medium text-sm">{subItem.name}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}

export function SidebarNavigation(props: NavigationProps) {
  return (
    <Suspense fallback={
      <aside
        className={`fixed left-0 top-0 h-full ${props.isDarkMode ? 'bg-gray-800' : 'bg-white'} border-r ${props.isDarkMode ? 'border-gray-700' : 'border-neutral-mid/10'} transition-all duration-300 z-40 ${props.isSidebarCollapsed ? 'w-20' : 'w-64'} hidden lg:block`}
      >
        <div className="h-16 flex items-center justify-center border-b border-neutral-mid/10">
          <div className="w-8 h-8 bg-gradient-to-br from-primary to-primary/80 rounded-lg animate-pulse"></div>
        </div>
      </aside>
    }>
      <SidebarNavigationContent {...props} />
    </Suspense>
  );
}
